"""管理员只读诊断：固定探针、白名单输出，不返回地址、路径或命令行。"""
import importlib.metadata
from itertools import islice
import os
from pathlib import Path
import platform
import shutil
import time

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

PROC = Path('/proc')
CGROUP = Path('/sys/fs/cgroup')
SAMPLE_SECONDS = 0.12
PROCESS_LIMIT = 128
DEPENDENCIES = ('Django', 'djangorestframework', 'celery', 'django-celery-beat',
                'redis', 'django-redis', 'gunicorn', 'psycopg2-binary', 'Pillow', 'pypdf')


def read(path):
    try:
        return path.read_text(encoding='utf-8')[:16384].strip()
    except (OSError, UnicodeError):
        return None


def number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def cpu_capacity():
    try:
        affinity = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count()
    except OSError:
        affinity = os.cpu_count()
    quota = (read(CGROUP / 'cpu.max') or '').split()
    if len(quota) == 2 and (number(quota[0]) or 0) > 0 and (number(quota[1]) or 0) > 0:
        return min(affinity or float('inf'), int(quota[0]) / int(quota[1]))
    return affinity


def cpu_counter(container):
    if container:
        counters = dict(line.split() for line in (read(CGROUP / 'cpu.stat') or '').splitlines() if len(line.split()) == 2)
        value = number(counters.get('usage_usec'))
        return (value / 1_000_000,) if value is not None else None
    fields = (read(PROC / 'stat') or '').splitlines()
    if not fields or not fields[0].startswith('cpu '):
        return None
    try:
        values = [int(value) for value in fields[0].split()[1:9]]
    except ValueError:
        return None
    return (sum(values), values[3] + (values[4] if len(values) > 4 else 0)) if len(values) >= 4 else None


def memory_snapshot(container):
    if container:
        used = number(read(CGROUP / 'memory.current'))
        limit = number(read(CGROUP / 'memory.max'))
        return {'used_bytes': used, 'total_bytes': limit, 'percent': round(used / limit * 100, 2) if used is not None and limit else None}
    values = {}
    for line in (read(PROC / 'meminfo') or '').splitlines():
        parts = line.split()
        if len(parts) >= 2:
            values[parts[0].rstrip(':')] = number(parts[1])
    total, available = values.get('MemTotal'), values.get('MemAvailable')
    used = (total - available) * 1024 if total is not None and available is not None else None
    return {'used_bytes': used, 'total_bytes': total * 1024 if total else None,
            'percent': round(used / (total * 1024) * 100, 2) if used is not None and total else None}


def processes():
    rows = []
    try:
        entries = sorted(islice((entry for entry in PROC.iterdir() if entry.name.isdigit()), PROCESS_LIMIT + 1), key=lambda entry: int(entry.name))
        ticks, page_size = os.sysconf('SC_CLK_TCK'), os.sysconf('SC_PAGE_SIZE')
        uptime = float((read(PROC / 'uptime') or '').split()[0])
    except (OSError, ValueError, IndexError, AttributeError):
        return [], False, False
    for entry in entries[:PROCESS_LIMIT]:
        raw = read(entry / 'stat')
        if not raw or ')' not in raw:
            continue
        fields = raw.rsplit(')', 1)[1].split()
        if len(fields) < 22:
            continue
        comm = raw[raw.find('(') + 1:raw.rfind(')')].lower()
        kind = 'python' if 'python' in comm or 'gunicorn' in comm else 'other'
        try:
            rows.append({'pid': int(entry.name), 'kind': kind, 'state': fields[0],
                         'cpu_seconds': round((int(fields[11]) + int(fields[12])) / ticks, 2),
                         'rss_bytes': max(0, int(fields[21])) * page_size,
                         'uptime_seconds': max(0, round(uptime - int(fields[19]) / ticks, 1))})
        except ValueError:
            continue
    return rows, len(entries) > PROCESS_LIMIT, True


def disk_snapshot():
    rows = []
    locations = [('application', settings.BASE_DIR), ('logs', settings.LOG_DIR)]
    if settings.ADMINCORE_STORAGE_BACKEND == 'local':
        locations.append(('media', settings.MEDIA_ROOT))
    for name, location in locations:
        try:
            usage = shutil.disk_usage(location)
            rows.append({'name': name, 'status': 'ok', 'total_bytes': usage.total,
                         'used_bytes': usage.used, 'free_bytes': usage.free,
                         'percent': round(usage.used / usage.total * 100, 2) if usage.total else None})
        except OSError:
            rows.append({'name': name, 'status': 'unavailable', 'total_bytes': None,
                         'used_bytes': None, 'free_bytes': None, 'percent': None})
    return rows


def resource_snapshot():
    container = Path('/.dockerenv').exists() or 'docker' in (read(PROC / '1/cgroup') or '') or 'kubepods' in (read(PROC / '1/cgroup') or '')
    capacity = cpu_capacity()
    before = cpu_counter(container)
    started = time.monotonic()
    if before is not None:
        time.sleep(SAMPLE_SECONDS)
    after = cpu_counter(container)
    elapsed = time.monotonic() - started
    percent = None
    if before is not None and after is not None:
        delta = after[0] - before[0]
        if container and capacity and delta >= 0:
            percent = delta / elapsed / capacity * 100
        elif not container and delta > 0:
            percent = (delta - (after[1] - before[1])) / delta * 100
    rows, truncated, supported = processes()
    return {'sampled_at': timezone.now().isoformat(), 'scope': 'container' if container else 'host',
            'cpu': {'capacity_cores': capacity, 'percent': round(max(0, min(100, percent)), 2) if percent is not None else None,
                    'sample_seconds': round(elapsed, 3) if before is not None else None},
            'memory': memory_snapshot(container), 'disks': disk_snapshot(),
            'processes': rows, 'processes_truncated': truncated, 'processes_supported': supported}


def redis_probe(name, url):
    started = time.monotonic()
    client = None
    try:
        client = Redis.from_url(url, socket_connect_timeout=0.35, socket_timeout=0.35,
                                retry=Retry(NoBackoff(), 0), retry_on_timeout=False)
        # Redis URL 查询参数优先级更高；再次固定实际连接参数，不能覆盖探针超时。
        client.connection_pool.connection_kwargs.update(socket_connect_timeout=0.35, socket_timeout=0.35,
                                                       retry=Retry(NoBackoff(), 0), retry_on_timeout=False,
                                                       health_check_interval=0)
        client.ping()
        version = client.info('server').get('redis_version')
        return {'name': name, 'status': 'ok', 'version': version, 'latency_ms': round((time.monotonic() - started) * 1000, 1)}
    except Exception:
        return {'name': name, 'status': 'unavailable', 'version': None, 'latency_ms': None}
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def service_snapshot():
    started = time.monotonic()
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                cursor.execute("SET LOCAL statement_timeout = '500ms'")
                cursor.execute('SHOW server_version')
            elif connection.vendor == 'sqlite':
                cursor.execute('SELECT sqlite_version()')
            else:
                cursor.execute('SELECT 1')
            value = cursor.fetchone()[0]
        database = {'name': 'database', 'status': 'ok', 'version': str(value) if connection.vendor in ('postgresql', 'sqlite') else None,
                    'latency_ms': round((time.monotonic() - started) * 1000, 1)}
    except Exception:
        database = {'name': 'database', 'status': 'unavailable', 'version': None, 'latency_ms': None}
    cache_config = settings.CACHES['default']
    if cache_config['BACKEND'] == 'django_redis.cache.RedisCache':
        cache = redis_probe('cache', cache_config['LOCATION'])
    else:
        cache = {'name': 'cache', 'status': 'in_process', 'version': None, 'latency_ms': None}
    services = [database, cache]
    if 'tasks' in settings.ADMINCORE_MODULES:
        services.append(redis_probe('broker', settings.CELERY_BROKER_URL))
    else:
        services.append({'name': 'broker', 'status': 'disabled', 'version': None, 'latency_ms': None})
    return services


def system_information():
    versions = []
    for name in DEPENDENCIES:
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            version = None
        versions.append({'name': name, 'version': version})
    return {'sampled_at': timezone.now().isoformat(), 'python': platform.python_version(),
            'os': platform.system(), 'architecture': platform.machine(),
            'environment': getattr(settings, 'ENV', None) or ('testing' if getattr(settings, 'TESTING', False) else os.getenv('DJANGO_ENV', 'development')),
            'debug': settings.DEBUG, 'preset': settings.ADMINCORE_PRESET,
            'modules': list(settings.ADMINCORE_MODULES), 'timezone': settings.TIME_ZONE,
            'database': connection.vendor, 'storage': settings.ADMINCORE_STORAGE_BACKEND,
            'dependencies': versions, 'services': service_snapshot()}
