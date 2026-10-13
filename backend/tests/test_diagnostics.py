"""只读诊断的权限、脱敏、故障退化和资源口径。"""
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.core import diagnostics as diag
from apps.core.diagnostic_views import DiagnosticThrottle
from apps.core.modules import path_enabled
from apps.permissions.models import Menu, Role, RolePermission

pytestmark = pytest.mark.django_db
INFO = '/api/v1/system/information/'
MONITOR = '/api/v1/system/monitor/'


@pytest.fixture(autouse=True)
def isolated_probes():
    DiagnosticThrottle.cache.clear()
    with patch.object(diag.Redis, 'from_url') as factory:
        factory.return_value.info.return_value = {'redis_version': '8.10.2', 'config_file': '/private', 'secret': 'credential'}
        yield factory
    DiagnosticThrottle.cache.clear()


def test_admin_only_read_only_no_store(admin_client, member_client, member_user):
    for endpoint in [INFO, MONITOR]:
        assert APIClient().get(endpoint).status_code == 401
        assert member_client.get(endpoint).status_code == 403
        response = admin_client.get(endpoint)
        assert response.status_code == 200
        assert response['Cache-Control'] == 'private, no-store'
        assert admin_client.post(endpoint, {}, format='json').status_code == 405
    role = Role.objects.create(name='诊断授权普通成员')
    from apps.permissions.models import Permission, UserRole
    permission = Permission.objects.create(resource='diagnostics', action='read', code='diagnostics:read', name='查看信息')
    RolePermission.objects.create(role=role, permission=permission)
    UserRole.objects.create(user=member_user, role=role)
    assert member_client.get(INFO).status_code == 403


def test_installed_versions_and_whitelist(admin_client, settings):
    settings.SECRET_KEY = 'private-secret-value'
    settings.CELERY_BROKER_URL = 'redis://name:private-password@private-host:6379/1'
    body = admin_client.get(INFO).json()['data']
    assert body['python'] == diag.platform.python_version()
    assert next(row for row in body['dependencies'] if row['name'] == 'Django')['version'] == diag.importlib.metadata.version('Django')
    assert body['database'] == 'sqlite'
    assert {item['name'] for item in body['services']} == {'database', 'cache', 'broker'}
    output = str(body)
    for sensitive in ['private-secret-value', 'private-password', 'private-host', '/private', 'config_file', 'credential']:
        assert sensitive not in output


def test_redis_failure_is_partial_and_bounded_configuration(admin_client, isolated_probes, settings):
    settings.CACHES = {'default': {'BACKEND': 'django_redis.cache.RedisCache', 'LOCATION': 'redis://fixture/0'}}
    isolated_probes.side_effect = TimeoutError('redis://private:secret@internal')
    response = admin_client.get(INFO)
    assert response.status_code == 200
    rows = response.json()['data']['services']
    assert rows[0]['status'] == 'ok'
    assert rows[1]['status'] == rows[2]['status'] == 'unavailable'
    assert 'secret' not in str(rows)
    assert isolated_probes.call_args.kwargs['socket_timeout'] == 0.35
    assert isolated_probes.call_args.kwargs['socket_connect_timeout'] == 0.35


def test_tasks_disabled_does_not_connect_broker(admin_client, settings, isolated_probes):
    settings.ADMINCORE_MODULES = ['system']
    assert admin_client.get(INFO).json()['data']['services'][-1]['status'] == 'disabled'
    isolated_probes.assert_not_called()


def test_url_query_cannot_override_timeout_or_retries(isolated_probes):
    from redis.connection import ConnectionPool
    client = diag.Redis(connection_pool=ConnectionPool.from_url('redis://fixture/0?socket_timeout=20&socket_connect_timeout=20&health_check_interval=60'))
    isolated_probes.return_value = client
    with patch.object(client, 'ping'), patch.object(client, 'info', return_value={'redis_version': '8.10.2'}):
        assert diag.redis_probe('cache', 'redis://fixture')['status'] == 'ok'
    options = client.connection_pool.connection_kwargs
    assert options['socket_timeout'] == options['socket_connect_timeout'] == 0.35
    assert options['health_check_interval'] == 0
    assert options['retry'].get_retries() == 0


def test_module_routes_close_and_reopen(admin_client, settings):
    settings.ADMINCORE_MODULES = []
    assert not path_enabled('/system/monitor')
    for endpoint in [INFO, MONITOR]:
        assert admin_client.get(endpoint).status_code == 404
    settings.ADMINCORE_MODULES = ['system']
    assert path_enabled('/system/information')
    assert admin_client.get(INFO).status_code == 200


def test_cpu_quota_and_cgroup_memory():
    values = {'cpu.max': '150000 100000', 'memory.current': '1024', 'memory.max': '2048', 'cpu.stat': 'usage_usec 1000000\nuser_usec 500000'}
    with patch.object(diag, 'read', side_effect=lambda path: values.get(path.name)), patch.object(diag.os, 'sched_getaffinity', create=True, return_value=set(range(8))):
        assert diag.cpu_capacity() == 1.5
        assert diag.cpu_counter(True) == (1.0,)
        assert diag.memory_snapshot(True) == {'used_bytes': 1024, 'total_bytes': 2048, 'percent': 50.0}
        values['memory.max'] = 'max'
        assert diag.memory_snapshot(True)['percent'] is None
        assert diag.memory_snapshot(True)['total_bytes'] is None
        values.pop('memory.current')
        assert diag.memory_snapshot(True)['used_bytes'] is None


def test_host_cpu_memory_and_no_proc_support(tmp_path):
    values = {'stat': 'cpu 10 0 20 60 10 0 0 0 0 0', 'meminfo': 'MemTotal: 2048 kB\nMemAvailable: 1024 kB'}
    with patch.object(diag, 'read', side_effect=lambda path: values.get(path.name)):
        assert diag.cpu_counter(False) == (100, 70)
        assert diag.memory_snapshot(False)['percent'] == 50
    with patch.object(diag, 'PROC', tmp_path / 'missing'):
        assert diag.processes() == ([], False, False)


def test_resource_sample_is_normalized_and_missing_not_zero():
    with patch.object(diag.Path, 'exists', return_value=True), patch.object(diag, 'cpu_capacity', return_value=2), \
         patch.object(diag, 'cpu_counter', side_effect=[(1.0,), (1.12,)]), \
         patch.object(diag.time, 'monotonic', side_effect=[0, 0.12]), patch.object(diag.time, 'sleep'), \
         patch.object(diag, 'processes', return_value=([], False, False)):
        row = diag.resource_snapshot()
        assert row['cpu']['percent'] == 50
        assert row['scope'] == 'container'
    with patch.object(diag, 'cpu_counter', return_value=None), patch.object(diag.time, 'sleep') as sleep:
        assert diag.resource_snapshot()['cpu']['percent'] is None
        sleep.assert_not_called()


def test_process_masking_counts_and_rss(tmp_path):
    (tmp_path / 'uptime').write_text('100.0 0.0')
    for pid in range(1, 131):
        folder = tmp_path / str(pid)
        folder.mkdir()
        fields = ['S'] + ['0'] * 21
        fields[11], fields[12], fields[19], fields[21] = '100', '200', '1000', '4'
        (folder / 'stat').write_text(f'{pid} (customer-secret.exe) ' + ' '.join(fields))
    with patch.object(diag, 'PROC', tmp_path), patch.object(diag.os, 'sysconf', create=True, side_effect=lambda name: 100 if name == 'SC_CLK_TCK' else 4096):
        rows, truncated, supported = diag.processes()
    assert len(rows) == 128 and truncated and supported
    assert rows[0] == {'pid': 1, 'kind': 'other', 'state': 'S', 'cpu_seconds': 3.0, 'rss_bytes': 16384, 'uptime_seconds': 90.0}
    assert 'customer-secret' not in str(rows)


def test_disk_failure_and_object_storage_no_local_media(settings):
    settings.ADMINCORE_STORAGE_BACKEND = 's3'
    with patch.object(diag.shutil, 'disk_usage', side_effect=OSError('secret-path')):
        rows = diag.disk_snapshot()
    assert len(rows) == 2 and all(row['status'] == 'unavailable' for row in rows)
    assert 'secret-path' not in str(rows)


def test_diag_throttle_and_failure_does_not_use_shared_cache(admin_client):
    with patch('django.core.cache.cache.get', side_effect=RuntimeError('cache unavailable')):
        for _ in range(30):
            assert admin_client.get(INFO).status_code == 200
        assert admin_client.get(MONITOR).status_code == 429


def test_bootstrap_preserves_existing_grants_and_menu_edits(admin_user, monkeypatch):
    admin_user.set_password('Existing-safe-fixture#2026')
    admin_user.save()
    monkeypatch.setenv('ADMINCORE_ADMIN_PASSWORD', 'unused-existing-user')
    role = Role.objects.create(name='系统管理员')
    call_command('bootstrap_admincore', stdout=StringIO())
    assert not RolePermission.objects.filter(role=role, permission__code__in=['diagnostics:read', 'monitor:read']).exists()
    menu = Menu.objects.get(path='/system/information')
    menu.name = '自定义名称'
    menu.save()
    Menu.objects.filter(path='/system/monitor').delete()
    call_command('bootstrap_admincore', stdout=StringIO())
    assert Menu.objects.get(pk=menu.pk).name == '自定义名称'
    assert not Menu.objects.filter(path='/system/monitor').exists()
