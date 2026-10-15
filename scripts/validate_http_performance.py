"""固定六服务HTTP回归负载；没有目标地址参数，只操作自建隔离空库。"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import math
import secrets
import socket
import statistics
import subprocess
import threading
import time
import uuid

import requests

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'admincore-http-performance-' + uuid.uuid4().hex[:8]
FOLDER = ROOT / '.codex-validation' / PROJECT
PORTS = [18490, 18491]
BASE = 'http://127.0.0.1:18491/api/v1/'
SERVICES = ['db', 'redis', 'backend', 'worker', 'beat', 'frontend']
SCENARIOS = {
    'users_first': ('users/?page_size=100', 50001),
    'users_deep': ('users/?page_size=100&page=400', 50001),
    'users_filtered': ('users/?is_active=true&page_size=100', 40001),
    'users_search': ('users/?search=benchmark_049&page_size=100', 1000),
    # 首次改密正常新增1条安全审计，不能为了固定计数删除它。
    'logs_first': ('logs/operation/?page_size=100', 100001),
    'logs_deep': ('logs/operation/?page_size=100&page=900', 100001),
    'logs_filtered': ('logs/operation/?resource=benchmark&page_size=100', 100000),
    'tasks_first': ('tasks/?page_size=100&status=success', 5000),
}
# 初始实际基线p95约235ms，留共享CI抖动余量；不能因后续失败自动放宽。
P95_MS = 800
P99_MS = 1500


def percentile(values, quantile):
    return sorted(values)[max(0, math.ceil(len(values) * quantile) - 1)]


def evaluate(samples, workers):
    """逐场景门槛，避免总体分位数掩盖低频慢接口；任何请求错误均失败。"""
    result = {}
    for name in SCENARIOS:
        rows = [row for row in samples if row['scenario'] == name]
        assert len(rows) == 20, '场景样本不足：' + name
        assert all(row['ok'] for row in rows), 'HTTP/分页契约失败：' + name
        durations = [row['milliseconds'] for row in rows]
        p95, p99 = percentile(durations, .95), percentile(durations, .99)
        result[name] = {'requests': len(rows), 'errors': 0, 'p50_ms': round(statistics.median(durations), 2),
                        'p95_ms': round(p95, 2), 'p99_ms': round(p99, 2)}
        assert p95 <= P95_MS and p99 <= P99_MS, '固定延迟门槛失败：' + name
    return {'workers': workers, 'requests': len(samples), 'scenarios': result}


def run(arguments, *, input=None, allowed_failure=False):
    result = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True, input=input,
                            encoding='utf-8', errors='replace', timeout=600)
    with (FOLDER / 'docker.log').open('a', encoding='utf-8') as output:
        output.write(result.stdout + result.stderr)
    if result.returncode and not allowed_failure:
        raise RuntimeError('隔离命令失败，见docker.log')
    return result


def compose(*arguments, input=None, allowed_failure=False):
    return run(['docker', 'compose', '-p', PROJECT, '--env-file', str(FOLDER / 'fixture.env'),
                '-f', 'docker-compose.yml', '-f', str(FOLDER / 'override.yml'), *arguments],
               input=input, allowed_failure=allowed_failure)


def snippet(code):
    prefix = "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); import django; django.setup(); from django.conf import settings; assert settings.DATABASES['default']['NAME']=='http_performance_fixture'\n"
    return compose('exec', '-T', 'backend', 'python', '-c', 'import sys; exec(sys.stdin.read())', input=prefix + code).stdout.strip()


def api(path, *, token=None, method='GET', expected=200, **kwargs):
    response = requests.request(method, BASE + path,
        headers={'Authorization': 'Bearer ' + token} if token else {}, timeout=15, **kwargs)
    assert response.status_code == expected, method + ' ' + path + ' status=' + str(response.status_code)
    return response


def seed(member_password):
    code = '''
from django.contrib.auth import get_user_model
from django.db import connection
from apps.logs.models import OperationLog
from apps.tasks.models import TaskRecord
User=get_user_model()
assert User.objects.count()==1 and not OperationLog.objects.exists() and not TaskRecord.objects.exists(), '只允许初始化独立空库'
admin=User.objects.get(username='admin')
for start in range(0,50000,2000):
    indices=range(start,start+2000)
    User.objects.bulk_create([User(username=f'benchmark_{i:06}',password='!',is_active=i%5!=0) for i in indices])
    OperationLog.objects.bulk_create([OperationLog(user=admin,action='read',resource='benchmark',ip_address='127.0.0.1',description=f'fixture {i}') for i in indices for _ in range(2)])
TaskRecord.objects.bulk_create([TaskRecord(name=f'benchmark history {i}',creator=admin,status='success',task_type='other') for i in range(5000)])
with connection.cursor() as cursor:
    cursor.execute('ANALYZE')
print('seeded')
'''
    code = code.replace("print('seeded')", """
from apps.permissions.models import Role, Permission, RolePermission, UserRole
from apps.core.models import DataScopeGrant
member=User.objects.get(username='benchmark_000001')
member.set_password(MEMBER_PASSWORD)
member.must_change_password=False
member.save()
role=Role.objects.create(name='benchmark self scope')
RolePermission.objects.create(role=role,permission=Permission.objects.get(code='user:read'))
UserRole.objects.create(role=role,user=member)
DataScopeGrant.objects.create(role=role,resource='user',scope='self')
print('seeded')
""")
    assert snippet('MEMBER_PASSWORD=' + repr(member_password) + '\n' + code) == 'seeded'


def request_sample(index, token):
    name = list(SCENARIOS)[index % len(SCENARIOS)]
    path, total = SCENARIOS[name]
    started = time.perf_counter()
    ok, status = False, None
    try:
        response = api(path, token=token)
        status = response.status_code
        body = response.json()['data']
        items = body['items']
        ok = (len(items) == 100 and body['pagination']['total'] == total
              and response.headers.get('Cache-Control') == 'private, no-store'
              and bool(response.headers.get('X-Request-ID')))
        if name.startswith('users'):
            ok = ok and all('password' not in row for row in items)
    except (AssertionError, requests.RequestException, KeyError, TypeError, ValueError):
        # 失败不输出响应体、JWT或请求头，继续收齐样本供定位。
        pass
    return {'scenario': name, 'ok': ok, 'status': status,
            'milliseconds': (time.perf_counter() - started) * 1000}


def queue_metrics():
    return json.loads(snippet('''
import json
from django.utils import timezone
from django.db.models import Count
from apps.tasks.models import TaskRecord
from redis import Redis
r=Redis.from_url(settings.CELERY_BROKER_URL,socket_timeout=2,socket_connect_timeout=2)
try:
    depths=[r.llen('celery'+suffix) for suffix in ['', '\\x06\\x163','\\x06\\x166','\\x06\\x169']]
    rows=TaskRecord.objects.filter(related_resource='maintenance:files')
    counts=dict(rows.values_list('status').annotate(count=Count('id')))
    durations=[(done-started).total_seconds() for started,done in rows.exclude(started_at=None).exclude(completed_at=None).values_list('started_at','completed_at')]
    now=timezone.now()
    oldest=rows.filter(status='pending').order_by('created_at').values_list('created_at',flat=True).first()
    print(json.dumps({'broker_ready':sum(depths),'registered_cleanup':counts,'max_execution_seconds':max(durations,default=None),'oldest_pending_seconds':(now-oldest).total_seconds() if oldest else 0}))
finally:
    r.close()
'''))


def container_snapshot():
    # 白名单格式避免Docker默认输出的容器名字、路径或环境。
    ids = compose('ps', '-q', *SERVICES).stdout.split()
    assert len(ids) == len(SERVICES)
    raw = run(['docker', 'stats', '--no-stream', '--format', '{{json .}}', *ids]).stdout
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    return [{'service': next(service for service in SERVICES if row['Name'].endswith('-' + service + '-1')),
             'cpu_percent': float(row['CPUPerc'].rstrip('%')), 'memory': row['MemUsage'],
             'memory_percent': float(row['MemPerc'].rstrip('%')), 'processes': row['PIDs']} for row in rows]


def resource_sampler(stop, rows, failures):
    started = time.monotonic()
    while not stop.is_set():
        try:
            rows.append({'elapsed_seconds': round(time.monotonic() - started, 3), 'containers': container_snapshot()})
        except Exception:
            failures.append('资源采样失败')
        stop.wait(.5)


def main():
    for port in PORTS:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', port))
    FOLDER.mkdir(parents=True)
    password, new_password, member_password = (secrets.token_urlsafe(40) for _ in range(3))
    env_file = FOLDER / 'fixture.env'
    environment = {'DJANGO_SECRET_KEY': secrets.token_urlsafe(60), 'DB_PASSWORD': secrets.token_urlsafe(40),
        'DB_NAME': 'http_performance_fixture', 'DB_USER': 'postgres', 'ADMINCORE_ADMIN_PASSWORD': password,
        'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend', 'DJANGO_ENV': 'production', 'DJANGO_DEBUG': 'False',
        'BACKEND_PORT': str(PORTS[0]), 'FRONTEND_PORT': str(PORTS[1]), 'AUTH_LOGIN_CAPTCHA_ENABLED': 'False',
        'ADMINCORE_MODULES': 'files,tasks,system', 'USE_TLS': 'False'}
    env_file.write_text(''.join(key + '=' + value + '\n' for key, value in environment.items()), encoding='utf-8')
    override = 'services:\n'
    for service in ['backend', 'worker', 'beat']:
        override += f'  {service}:\n    env_file: !override\n      - "{env_file.as_posix()}"\n    image: {PROJECT}-backend\n    cpus: 2\n    mem_limit: 1g\n'
        if service == 'worker':
            # 此批测单消费者排队，防止维护互斥使短任务按重叠跳过。
            override += '    command: celery -A config worker -l info --concurrency=1\n'
    override += f'  db:\n    cpus: 2\n    mem_limit: 1g\n  redis:\n    cpus: 1\n    mem_limit: 256m\n  frontend:\n    image: {PROJECT}-frontend\n    cpus: 1\n    mem_limit: 256m\n    ports: !override\n      - "127.0.0.1:{PORTS[1]}:80"\n'
    (FOLDER / 'override.yml').write_text(override, encoding='utf-8')
    report = {'passed': False, 'project': PROJECT, 'ports': PORTS, 'scenarios': SCENARIOS,
              'thresholds': {'per_scenario_p95_ms': P95_MS, 'per_scenario_p99_ms': P99_MS, 'max_errors': 0},
              'boundary': 'loopback HTTP + Nginx + Gunicorn 3 workers + JWT/session/permission + PostgreSQL; no TLS/public RTT; original throttles unchanged',
              'resources': [], 'loads': [], 'queue': []}
    stop, sampler = threading.Event(), None
    sampler_failures = []
    try:
        compose('build', 'backend', 'frontend')
        compose('up', '-d', '--wait', '--wait-timeout', '180')
        assert set(compose('ps', '--status', 'running', '--services').stdout.split()) == set(SERVICES)
        report['docker_environment'] = json.loads(run(['docker', 'info', '--format',
            '{"cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}},"server_version":"{{.ServerVersion}}","architecture":"{{.Architecture}}"}']).stdout)
        report['resource_limits'] = {}
        for service in SERVICES:
            container_id = compose('ps', '-q', service).stdout.strip()
            limits = json.loads(run(['docker', 'inspect', '--format',
                '{"nano_cpus":{{.HostConfig.NanoCpus}},"memory_bytes":{{.HostConfig.Memory}}}', container_id]).stdout)
            expected = {'nano_cpus': 1000000000, 'memory_bytes': 256 * 1024 ** 2} if service in ['redis', 'frontend'] else {'nano_cpus': 2000000000, 'memory_bytes': 1024 ** 3}
            assert limits == expected, '容器资源限制未生效：' + service
            report['resource_limits'][service] = limits
        seed(member_password)
        token = api('auth/login/', method='POST', json={'username': 'admin', 'password': password}).json()['access']
        api('auth/change_password/', token=token, method='POST', json={'old_password': password, 'new_password': new_password, 'new_password2': new_password})
        token = api('auth/login/', method='POST', json={'username': 'admin', 'password': new_password}).json()['access']
        api('users/', expected=401)
        member_token = api('auth/login/', method='POST', json={'username': 'benchmark_000001', 'password': member_password}).json()['access']
        member_page = api('users/', token=member_token).json()['data']
        assert member_page['pagination']['total'] == 1 and member_page['items'][0]['username'] == 'benchmark_000001'
        api('logs/operation/', token=member_token, expected=403)
        report['authorization'] = {'anonymous_rejected': True, 'member_self_only': True, 'member_logs_denied': True}
        # 每场景3次热身，包含实际签名与认证；正式限流未修改。
        warmup = [request_sample(index, token) for index in range(len(SCENARIOS) * 3)]
        report['warmup'] = warmup
        assert all(row['ok'] for row in warmup), '热身契约失败，见report.json逐场景结果'
        report['queue'].append(queue_metrics())
        sampler = threading.Thread(target=resource_sampler, args=(stop, report['resources'], sampler_failures), daemon=True)
        sampler.start()
        for workers in [1, 8]:
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=workers) as executor:
                samples = list(executor.map(lambda index: request_sample(index, token), range(160)))
            # 先保存原样本，即使门槛失败也留下逐请求证据。
            (FOLDER / f'samples-{workers}.json').write_text(json.dumps(samples, indent=2), encoding='utf-8')
            summary = evaluate(samples, workers)
            summary['elapsed_seconds'] = round(time.perf_counter() - started, 3)
            summary['requests_per_second'] = round(160 / summary['elapsed_seconds'], 2)
            report['loads'].append(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
        snippet("from apps.tasks.tasks import cleanup_soft_deleted_files\nfor _ in range(12): cleanup_soft_deleted_files.delay(dry_run=True)")
        deadline = time.monotonic() + 60
        while True:
            metrics = queue_metrics()
            report['queue'].append(metrics)
            if metrics['registered_cleanup'].get('success') == 12 and metrics['broker_ready'] == 0:
                break
            assert time.monotonic() < deadline, '真实干跑任务超时/失联'
            assert not metrics['registered_cleanup'].get('failed'), '真实干跑任务失败'
            time.sleep(1)
        assert metrics['max_execution_seconds'] is not None and metrics['max_execution_seconds'] <= 30
        assert snippet("from apps.tasks.models import TaskRecord; assert TaskRecord.objects.filter(related_resource='maintenance:files',status='success',result__dry_run=True).count()==12; print('actual dry runs')") == 'actual dry runs'
        stop.set()
        sampler.join(timeout=20)
        assert not sampler.is_alive() and not sampler_failures and report['resources'], '资源采样不完整'
        assert all(len(sample['containers']) == 6 and all(row['memory_percent'] < 95 for row in sample['containers']) for sample in report['resources']), '容器内存接近上限'
        ids = compose('ps', '-q', *SERVICES).stdout.split()
        states = run(['docker', 'inspect', '--format', '{{.RestartCount}} {{.State.OOMKilled}} {{.State.Running}}', *ids]).stdout.splitlines()
        assert len(states) == 6 and all(row == '0 false true' for row in states), '容器重启/OOM/退出'
        report['container_states'] = states
        report['fixture_counts'] = json.loads(snippet("from django.contrib.auth import get_user_model; from apps.logs.models import OperationLog; from apps.tasks.models import TaskRecord; import json; print(json.dumps({'users':get_user_model().objects.count(),'logs':OperationLog.objects.filter(resource='benchmark').count(),'history_tasks':TaskRecord.objects.filter(name__startswith='benchmark history ').count()}))"))
        assert report['fixture_counts'] == {'users': 50001, 'logs': 100000, 'history_tasks': 5000}
        report['passed'] = True
    finally:
        stop.set()
        if sampler:
            sampler.join(timeout=20)
        if report['passed']:
            compose('down', '-v', '--remove-orphans')
            env_file.unlink()
            report['cleaned'] = ['isolated containers and volumes', str(env_file)]
        else:
            compose('logs', '--no-color', allowed_failure=True)
        (FOLDER / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'evidence': str(FOLDER), 'passed': report['passed']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
