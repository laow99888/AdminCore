"""管理员只读诊断：固定探针、白名单输出，不返回地址、路径或命令行。"""
import importlib.metadata
from datetime import timedelta
from itertools import islice
import math
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

from .models import OutboxEvent

PROC = Path('/proc')
CGROUP = Path('/sys/fs/cgroup')
SAMPLE_SECONDS = 0.12
PROCESS_LIMIT = 128
DEPENDENCIES = ('Django', 'djangorestframework', 'celery', 'django-celery-beat',
                'redis', 'django-redis', 'gunicorn', 'psycopg2-binary', 'Pillow', 'pypdf')


def _percentile(values, percentile):
    """Return a bounded nearest-rank percentile without exposing task data."""
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * percentile) - 1))], 3)


def _queue_snapshot():
    """Read only Celery queue lengths with a hard connection timeout."""
    if 'tasks' not in settings.ADMINCORE_MODULES:
        return {'status': 'disabled', 'ready': None}
    client = None
    # Kombu's Redis transport uses these list names for the default queue and
    # priority buckets.  They are implementation details, so the response
    # exposes only counts and never the broker URL or key names.
    queue_names = ('celery', 'celery\x06\x163', 'celery\x06\x166', 'celery\x06\x169')
    try:
        client = Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=0.35,
                                socket_timeout=0.35, retry=Retry(NoBackoff(), 0),
                                retry_on_timeout=False)
        client.connection_pool.connection_kwargs.update(socket_connect_timeout=0.35,
                                                        socket_timeout=0.35,
                                                        retry=Retry(NoBackoff(), 0),
                                                        retry_on_timeout=False,
                                                        health_check_interval=0)
        values = []
        for key in queue_names:
            value = client.llen(key)
            if type(value) is not int or value < 0:
                raise ValueError('invalid_queue_length')
            values.append(value)
        return {'status': 'ok', 'ready': sum(values)}
    except Exception:
        return {'status': 'unavailable', 'ready': None}
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def _age_seconds(value, now):
    return round(max(0.0, (now - value).total_seconds()), 3) if value else None


def _empty_task_snapshot():
    return {
        'status': 'disabled' if 'tasks' not in settings.ADMINCORE_MODULES else 'ok',
        'task_records': {'counts': None, 'lost_candidates': None,
                         'duration_seconds': None},
        'outbox': {'counts': None, 'oldest_pending_seconds': None, 'oldest_failed_seconds': None},
        'notifications': {'status': 'disabled', 'counts': None, 'oldest_pending_seconds': None,
                          'oldest_failed_seconds': None},
        'broker': {'status': 'disabled', 'ready': None},
        'correlation': {'outbox_request_linked': None, 'task_request_linked': None,
                        'notification_request_linked': None},
    }


def task_snapshot():
    """只读汇总；每条SQL最多500ms，数据失败时不将未知指标显示为0。"""
    empty = _empty_task_snapshot()
    empty['broker'] = _queue_snapshot()
    if 'tasks' not in settings.ADMINCORE_MODULES:
        return empty
    try:
        with transaction.atomic():
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '500ms'")
            return _database_task_snapshot(empty)
    except Exception:
        failed = _empty_task_snapshot()
        failed['broker'] = empty['broker']
        failed['status'] = 'degraded'
        if 'notifications' in settings.ADMINCORE_MODULES:
            failed['notifications']['status'] = 'unavailable'
        return failed


def _database_task_snapshot(empty):
    now = timezone.now()
    try:
        from django.db.models import Count
        from apps.tasks.models import TaskRecord, MaintenanceRequest, ImportExecution
        records = TaskRecord.objects.all()
        empty['task_records']['counts'] = dict(records.values('status').annotate(count=Count('id'))
                                               .values_list('status', 'count'))
        # 仅按持久化策略检测最早的1000条活跃任务；旧记录没有策略时不猜测。
        active = list(records.filter(status__in=['pending', 'running'])
                      .select_related('maintenance_request', 'import_execution')
                      .only('id', 'status', 'created_at', 'started_at', 'maintenance_request__record_id',
                            'maintenance_request__policy', 'import_execution__record_id', 'import_execution__policy')
                      .order_by('created_at', 'pk')[:1001])
        lost = {'pending': 0, 'running': 0, 'sampled': min(len(active), 1000),
                'unclassified': 0, 'truncated': len(active) > 1000}
        for row in active[:1000]:
            execution = getattr(row, 'maintenance_request', None) or getattr(row, 'import_execution', None)
            policy = execution.policy if execution and isinstance(execution.policy, dict) else {}
            if (type(policy.get('queue_expiry')) is not int or type(policy.get('hard_timeout')) is not int
                    or policy['queue_expiry'] <= 0 or policy['hard_timeout'] <= 0):
                lost['unclassified'] += 1
                continue
            anchor = row.created_at if row.status == 'pending' else row.started_at
            timeout = policy['queue_expiry'] if row.status == 'pending' else policy['hard_timeout'] + 60
            if anchor is None:
                lost['unclassified'] += 1
            elif anchor < now - timedelta(seconds=timeout):
                lost[row.status] += 1
        empty['task_records']['lost_candidates'] = lost
        durations = []
        recent = records.filter(status__in=['success', 'failed', 'cancelled'],
                                started_at__isnull=False, completed_at__isnull=False)
        for started, completed in recent.order_by('-completed_at', 'pk').values_list('started_at', 'completed_at')[:1000]:
            duration = (completed - started).total_seconds()
            if duration >= 0:
                durations.append(duration)
        empty['task_records']['duration_seconds'] = {
            'count': len(durations), 'average': round(sum(durations) / len(durations), 3) if durations else None,
            'p95': _percentile(durations, .95), 'max': round(max(durations), 3) if durations else None,
        }
        outbox = OutboxEvent.objects.all()
        empty['outbox']['counts'] = dict(outbox.values('status').annotate(count=Count('id'))
                                         .values_list('status', 'count'))
        for state in ('pending', 'failed'):
            row = outbox.filter(status=state).order_by('created_at').values_list('created_at', flat=True).first()
            empty['outbox'][f'oldest_{state}_seconds'] = _age_seconds(row, now)
        empty['correlation']['outbox_request_linked'] = outbox.exclude(request_id='').count()
        empty['correlation']['task_request_linked'] = (
            MaintenanceRequest.objects.exclude(request_id='').count()
            + ImportExecution.objects.exclude(request_id='').count())
    except Exception:
        empty['status'] = 'degraded'
    if 'notifications' in settings.ADMINCORE_MODULES:
        try:
            from apps.notifications.models import MessageDelivery
            deliveries = MessageDelivery.objects.all()
            empty['notifications']['status'] = 'ok'
            empty['notifications']['counts'] = dict(deliveries.values('status').annotate(count=Count('id'))
                                                    .values_list('status', 'count'))
            for state in ('pending', 'failed'):
                row = deliveries.filter(status=state).order_by('created_at').values_list('created_at', flat=True).first()
                empty['notifications'][f'oldest_{state}_seconds'] = _age_seconds(row, now)
            empty['correlation']['notification_request_linked'] = deliveries.exclude(request_id='').count()
        except Exception:
            empty['notifications']['status'] = 'unavailable'
    return empty


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
            'dependencies': versions, 'services': service_snapshot(), 'task_metrics': task_snapshot()}
