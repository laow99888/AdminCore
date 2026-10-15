"""只在 foundation 隔离 PostgreSQL 取消真实 SQL、竞争真实锁并核对连接恢复。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, connections, transaction
from django.test import override_settings
from rest_framework.test import APIClient

from apps.core.exceptions import APIError
from apps.core.query_budget import query_budget
from apps.users.views import UserViewSet
from apps.data_io import views as export_views
from apps.logs.models import OperationLog

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connection.vendor == 'postgresql', '必须使用 PostgreSQL'
actor = get_user_model().objects.get(username='admin')
client = APIClient(HTTP_HOST='localhost')
client.force_authenticate(actor)


def limits():
    with connection.cursor() as cursor:
        cursor.execute("SELECT name, setting FROM pg_settings WHERE name IN ('statement_timeout', 'lock_timeout')")
        return dict(cursor.fetchall())


def usable():
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        assert cursor.fetchone() == (1,)


def slow_sql():
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_sleep(1)')
    except DatabaseError as exc:
        assert (getattr(exc.__cause__, 'sqlstate', None) or getattr(exc.__cause__, 'pgcode', None)) == '57014'
        raise


def timeout_response(response):
    assert response.status_code == 503, response.status_code
    assert response.json() == {'code': 503, 'message':
        '查询超时或等待锁过久，请缩小筛选范围后重试', 'data': None}
    assert 'Content-Disposition' not in response
    usable()


initial = limits()
with override_settings(ADMINCORE_QUERY_STATEMENT_TIMEOUT_MS=50, ADMINCORE_QUERY_LOCK_TIMEOUT_MS=30):
    with query_budget():
        assert limits() == {'statement_timeout': '50', 'lock_timeout': '30'}
    assert limits() == initial
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '40ms'")
            cursor.execute("SET LOCAL lock_timeout = '20ms'")
        with query_budget():
            assert limits() == {'statement_timeout': '40', 'lock_timeout': '20'}
            with override_settings(ADMINCORE_QUERY_STATEMENT_TIMEOUT_MS=10):
                with query_budget():
                    assert limits()['statement_timeout'] == '10'
            assert limits()['statement_timeout'] == '40'
        assert limits() == {'statement_timeout': '40', 'lock_timeout': '20'}
        try:
            with query_budget():
                slow_sql()
        except APIError as exc:
            assert exc.status_code == 503
        else:
            raise AssertionError('未取消耗时 SQL')
        usable()
        assert limits() == {'statement_timeout': '40', 'lock_timeout': '20'}
    assert limits() == initial
    print('通过：真实局部预算、严格外层限制、嵌套恢复及超时 savepoint 回滚', flush=True)

    def slow_users(view):
        slow_sql()
        return original_users(view)

    original_users = UserViewSet.get_queryset
    with patch.object(UserViewSet, 'get_queryset', slow_users):
        timeout_response(client.get('/api/v1/users/'))
    assert limits() == initial
    assert client.get('/api/v1/users/').status_code == 200
    print('通过：真实 pg_sleep 取消用户列表并返回无 SQL 内容的 503，原连接恢复', flush=True)

    original_export = export_views.export_queryset

    def slow_export(*args, **kwargs):
        slow_sql()
        return original_export(*args, **kwargs)

    with patch.object(export_views, 'export_queryset', slow_export):
        for output in ['csv', 'xlsx']:
            timeout_response(client.get('/api/v1/data-io/export/', {'resource': 'users', 'export_format': output}))
    assert limits() == initial
    print('通过：真实导出 SQL 被取消，CSV/XLSX 均未返回部分文件', flush=True)

    audit_count = OperationLog.objects.filter(resource='data_io', action='export').count()
    original_log = export_views._log

    def slow_audit(*args, **kwargs):
        original_log(*args, **kwargs)
        slow_sql()

    with patch.object(export_views, '_log', slow_audit):
        timeout_response(client.get('/api/v1/data-io/export/', {'resource': 'users'}))
    assert OperationLog.objects.filter(resource='data_io', action='export').count() == audit_count
    assert limits() == initial
    print('通过：导出已写审计后发生 SQL 超时，审计回滚且文件未发送', flush=True)

    held, release = Event(), Event()

    def hold_table():
        try:
            with transaction.atomic():
                with connections['default'].cursor() as cursor:
                    cursor.execute('LOCK TABLE auth_app_user IN ACCESS EXCLUSIVE MODE')
                held.set()
                assert release.wait(15), '锁测试未及时释放'
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold_table)
        try:
            assert held.wait(10)
            try:
                with query_budget():
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT id FROM auth_app_user LIMIT 1')
                    except DatabaseError as exc:
                        assert (getattr(exc.__cause__, 'sqlstate', None) or getattr(exc.__cause__, 'pgcode', None)) == '55P03'
                        raise
            except APIError as exc:
                assert exc.status_code == 503
            else:
                raise AssertionError('未取消真实锁等待')
            timeout_response(client.get('/api/v1/users/'))
            timeout_response(client.get('/api/v1/data-io/export/', {'resource': 'users'}))
        finally:
            release.set()
        future.result()
    assert limits() == initial
    assert client.get('/api/v1/users/').status_code == 200
    assert client.get('/api/v1/data-io/export/', {'resource': 'users'}).status_code == 200
    print('通过：真实表锁等待被取消，释放后列表/导出恢复且连接预算无残留', flush=True)

    try:
        with query_budget():
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1 / 0')
    except DatabaseError as exc:
        assert (getattr(exc.__cause__, 'sqlstate', None) or getattr(exc.__cause__, 'pgcode', None)) == '22012'
    else:
        raise AssertionError('普通数据库异常被吞掉')
    usable()
    assert limits() == initial
    print('通过：非预算数据库异常保持原错误类型，不伪装为超时', flush=True)
