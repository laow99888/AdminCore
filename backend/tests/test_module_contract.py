"""模块启停覆盖直接入口、后台消费、导航、计划保留及配置组合。"""
from io import StringIO
import pytest
from celery.exceptions import Ignore
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import override_settings
from django_celery_beat.models import PeriodicTask
from apps.core.modules import resolve_modules, task_enabled
from apps.permissions.models import Menu
from apps.notifications.models import Notification
from apps.tasks.models import TaskRecord

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('preset,explicit', [('unknown', None), ('standard', 'files,files'),
                                          ('minimal', 'data_io'), ('standard', 'approvals'), ('standard', 'unknown')])
def test_invalid_module_config_rejected(preset, explicit):
    with pytest.raises(ImproperlyConfigured):
        resolve_modules(preset, explicit)


def test_presets_and_production_demo_guard():
    assert resolve_modules('minimal') == ()
    assert set(resolve_modules('standard')) == {'files', 'tasks', 'notifications', 'data_io', 'approvals', 'system', 'organization'}
    with pytest.raises(ImproperlyConfigured):
        resolve_modules('demo', production=True)
    assert resolve_modules('minimal', 'files') == ('files',)


def test_disabled_api_admin_and_navigation_reenable_without_data_loss(admin_client, member_user):
    root = Menu.objects.create(name='文件', path='/files')
    Menu.objects.create(name='子项', path='/files/private', parent=root)
    retained = Notification.objects.create(recipient=member_user, title='保留通知')
    with override_settings(ADMINCORE_PRESET='minimal', ADMINCORE_MODULES=()):
        for path in ['/api/v1/files/', '/api/v1/tasks/', '/api/v1/data-io/export/', '/api/v1/approvals/',
                     '/api/v1/notifications/', '/api/v1/system/config/', '/api/v1/organization/departments/', '/admin/files/filemodel/']:
            assert admin_client.get(path).status_code == 404
        assert admin_client.get('/api/v1/permissions/menus/my_menu/').json()['data'] == []
        assert Notification.push([member_user.pk], '关闭不发送') == 0
        assert Notification.objects.filter(pk=retained.pk).exists()
        data = admin_client.get('/api/v1/modules/').json()['data']
        assert data['contract_version'] == 1 and not any(module['enabled'] for module in data['modules'])
    assert admin_client.get('/api/v1/files/').status_code == 200
    assert admin_client.get('/api/v1/permissions/menus/my_menu/').json()['data'][0]['id'] == str(root.pk)
    assert Notification.objects.filter(pk=retained.pk).exists()


def test_disabled_task_no_business_writes():
    from apps.tasks.tasks import cleanup_expired_notifications
    with override_settings(ADMINCORE_MODULES=()):
        with pytest.raises(Ignore):
            cleanup_expired_notifications()
    assert TaskRecord.objects.count() == 0


def test_disabled_schedule_preserved_and_filtered():
    from config.celery import app
    from apps.core.module_scheduler import ModuleScheduler
    call_command('configure_maintenance', stdout=StringIO())
    # 上游调度器会剔除当前时段之外的 cron，使用任意小时隔离此测试的时间依赖。
    from django_celery_beat.models import CrontabSchedule
    CrontabSchedule.objects.update(hour='*')
    with override_settings(ADMINCORE_MODULES=()):
        call_command('configure_maintenance', stdout=StringIO())
        scheduler = ModuleScheduler(app=app, lazy=True)
        assert scheduler.enabled_models_qs().count() == 3
        assert PeriodicTask.objects.filter(enabled=True).count() == 5
        assert not task_enabled('tasks.cleanup_expired_notifications')
        assert not task_enabled('arbitrary.function')
    assert ModuleScheduler(app=app, lazy=True).enabled_models_qs().count() == 5


def test_minimal_dashboard_no_disabled_table_reads(admin_client, django_assert_num_queries):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    with override_settings(ADMINCORE_MODULES=()):
        with CaptureQueriesContext(connection) as queries:
            response = admin_client.get('/api/v1/dashboard/stats/')
    assert response.status_code == 200
    assert response.json()['data']['totals']['files'] == 0
    assert response.json()['data']['task_status'] == {}
    for query in queries:
        assert all(table not in query['sql'] for table in ['files_filemodel', 'tasks_taskrecord', 'notifications_notification', 'approvals_approvalrequest'])


def test_minimal_health_does_not_require_redis(client):
    from unittest.mock import patch
    with override_settings(ADMINCORE_MODULES=(), CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}):
        with patch('django_redis.get_redis_connection', side_effect=AssertionError('不应连接 Redis')):
            assert client.get('/api/v1/health/').status_code == 200
