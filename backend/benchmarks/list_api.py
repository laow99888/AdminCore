"""仅针对独立空库的 PostgreSQL 列表基准；不使用项目 .env 的数据库凭据。

示例：ADMINCORE_BENCHMARK_PASSWORD=... python benchmarks/list_api.py --port 18432 --output report.json
数据库必须名为 admincore_benchmark_quality；脚本拒绝已有用户数据，保留测试库供复查。
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--rows', type=int, default=50000)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--verify-existing-fixtures', action='store_true', help='复查本脚本创建的独立测试库，拒绝任何其他用户名')
args = parser.parse_args()
if not 1000 <= args.rows <= 100000:
    parser.error('--rows 必须在 1000 到 100000 之间')
password = os.environ['ADMINCORE_BENCHMARK_PASSWORD']
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.testing'
from config.settings import testing
testing.DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql',
    'NAME': 'admincore_benchmark_quality', 'USER': 'benchmark', 'PASSWORD': password,
    'HOST': '127.0.0.1', 'PORT': args.port, 'CONN_MAX_AGE': 0}}
testing.DEBUG = False
testing.ALLOWED_HOSTS = ['testserver']
testing.REST_FRAMEWORK = {**testing.REST_FRAMEWORK, 'DEFAULT_THROTTLE_CLASSES': []}
import django
django.setup()
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext
from apps.logs.models import OperationLog
from apps.tasks.models import TaskRecord
from apps.files.models import FileModel
from rest_framework.test import APIClient
User = get_user_model()
call_command('migrate', verbosity=0)
existing = User.objects.exists()
if existing and not args.verify_existing_fixtures:
    raise SystemExit('拒绝覆盖已有用户数据；请新建独立空基准库')
if existing and User.objects.exclude(username__startswith='benchmark_').exists():
    raise SystemExit('拒绝操作含非基准用户的库')
admin = User.objects.get(username='benchmark_admin') if existing else User.objects.create_superuser('benchmark_admin', password='BenchmarkFixture#2948')
for start in range(0, 0 if existing else args.rows, 2000):
    indices = range(start, min(start + 2000, args.rows))
    User.objects.bulk_create([User(username=f'benchmark_{i:06}', email=f'bench{i}@example.com', is_active=i % 5 != 0, password='!') for i in indices])
    OperationLog.objects.bulk_create([OperationLog(user=admin, action='read', resource='benchmark', description=f'fixture {i}', ip_address='127.0.0.1') for i in indices for _ in range(2)])
    TaskRecord.objects.bulk_create([TaskRecord(name=f'benchmark task {i}', creator=admin, status=['success', 'failed', 'pending'][i % 3]) for i in indices])
    FileModel.objects.bulk_create([FileModel(original_name=f'benchmark{i}.txt', uploader=admin, is_deleted=i % 5 == 0, size=32, file_type='txt') for i in indices])
with connection.cursor() as cursor:
    cursor.execute('ANALYZE')
client = APIClient()
client.force_authenticate(admin)
scenarios = {
    'users_first': '/api/v1/users/?page_size=100',
    'users_deep': '/api/v1/users/?page_size=100&page=400',
    'users_filtered': '/api/v1/users/?is_active=true&page_size=100',
    'users_search': '/api/v1/users/?search=benchmark_049&page_size=100',
    'logs_first': '/api/v1/logs/operation/?page_size=100',
    'tasks_first': '/api/v1/tasks/?page_size=100',
    'tasks_filtered': '/api/v1/tasks/?status=success&page_size=100',
    'files_first': '/api/v1/files/?page_size=100',
}
def measure():
    result = {}
    for name, url in scenarios.items():
        durations = []
        plans = []
        for run in range(10):
            begin = time.perf_counter()
            with CaptureQueriesContext(connection) as captured:
                response = client.get(url)
            elapsed = (time.perf_counter() - begin) * 1000
            assert response.status_code == 200, (name, response.status_code, response.content[:200])
            data = response.json()['data']
            assert len(data['items']) <= 100 and data['pagination']['total'] > 0
            durations.append(elapsed)
            if run == 9:
                for query in captured.captured_queries:
                    if query['sql'].startswith('SELECT') and 'LIMIT' in query['sql']:
                        with connection.cursor() as cursor:
                            cursor.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + query['sql'])
                            plans.append(cursor.fetchone()[0])
        result[name] = {'p50_ms': round(statistics.median(durations), 2), 'p95_ms': round(sorted(durations)[-1], 2),
                        'queries': len(captured), 'total': data['pagination']['total'], 'plans': plans}
    return result
current = measure()
urls = list(scenarios.values())
def concurrent_request(index):
    thread_client = APIClient()
    thread_client.force_authenticate(admin)
    begin = time.perf_counter()
    try:
        response = thread_client.get(urls[index % len(urls)])
        return response.status_code, (time.perf_counter() - begin) * 1000
    finally:
        connections.close_all()
begin = time.perf_counter()
with ThreadPoolExecutor(max_workers=8) as pool:
    samples = list(pool.map(concurrent_request, range(200)))
elapsed = time.perf_counter() - begin
assert all(status == 200 for status, _ in samples)
durations = sorted(duration for _, duration in samples)
from apps.permissions.models import Menu
from threading import Barrier
menu_a, _ = Menu.objects.get_or_create(path='/benchmark-a', defaults={'name': 'A'})
menu_b, _ = Menu.objects.get_or_create(path='/benchmark-b', defaults={'name': 'B'})
Menu.objects.filter(pk__in=[menu_a.pk, menu_b.pk]).update(parent=None)
barrier = Barrier(2)
def move_menu(pair):
    item, parent = pair
    thread_client = APIClient()
    thread_client.force_authenticate(admin)
    try:
        barrier.wait(timeout=10)
        return thread_client.patch(f'/api/v1/permissions/menus/{item.pk}/', {'parent': str(parent.pk)}, format='json').status_code
    finally:
        connections.close_all()
with ThreadPoolExecutor(max_workers=2) as pool:
    menu_statuses = sorted(pool.map(move_menu, [(menu_a, menu_b), (menu_b, menu_a)]))
assert menu_statuses == [200, 400], menu_statuses
menu_a.refresh_from_db()
menu_b.refresh_from_db()
assert not (menu_a.parent_id == menu_b.pk and menu_b.parent_id == menu_a.pk)
report = {'database': 'PostgreSQL 18.6, dedicated empty container',
          'rows': {'users': User.objects.count(), 'logs': OperationLog.objects.count(), 'tasks': TaskRecord.objects.count(), 'files': FileModel.objects.count()},
          'boundary': 'Django APIClient + PostgreSQL; excludes network/TLS/JWT verification; throttling disabled in this isolated benchmark only',
          'current': current,
          'concurrent_menu_cycle': {'statuses': menu_statuses, 'cycle_created': False},
          'concurrent': {'workers': 8, 'requests': 200, 'errors': 0, 'requests_per_second': round(200 / elapsed, 2),
                         'p50_ms': round(statistics.median(durations), 2), 'p95_ms': round(durations[189], 2)}}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in report.items() if key != 'current'}, ensure_ascii=False, indent=2))
for name in scenarios:
    print(name, 'p50:', current[name]['p50_ms'], 'queries:', current[name]['queries'])
connections.close_all()
