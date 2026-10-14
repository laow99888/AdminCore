"""有界历史清理、预览策略、存储失败和导入重试保护。"""
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from django_celery_beat.models import PeriodicTask

from apps.core.models import SystemConfig
from apps.files.models import FileModel
from apps.logs.models import OperationLog, LoginLog, ExceptionLog
from apps.tasks.lifecycle import clean, policy
from apps.tasks.models import TaskRecord
from apps.tasks.tasks import cleanup_lifecycle, run_maintenance

pytestmark = pytest.mark.django_db
BASE = '/api/v1/tasks/schedules/'


def old(row, days=400):
    type(row).objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(days=days))
    return row


def source(owner, purpose='import', days=400):
    return old(FileModel.objects.create(original_name='source.csv',
        file=SimpleUploadedFile('source.csv', b'username\nu1'), purpose=purpose,
        uploader=owner, size=11), days)


def row(client):
    return next(item for item in client.get(BASE).json()['data'] if item['key'] == 'lifecycle')


def submit(client, dry_run=True, preview_id=None, idem='preview'):
    return client.post(BASE + 'lifecycle/run/', {'revision': row(client)['revision'],
        'options': {'dry_run': dry_run}, 'preview_id': preview_id,
        'confirmation': '执行清理' if not dry_run else ''}, format='json', HTTP_IDEMPOTENCY_KEY=idem)


def test_default_plan_disabled_and_preserves_edits():
    call_command('configure_maintenance', stdout=StringIO())
    plan = PeriodicTask.objects.get(task='tasks.cleanup_lifecycle')
    assert not plan.enabled and plan.crontab.hour == '4'
    plan.enabled = True
    plan.save()
    call_command('configure_maintenance', stdout=StringIO())
    plan.refresh_from_db()
    assert plan.enabled


def test_console_logging_default_avoids_shared_worker_file():
    from config.settings.base import LOGGING
    assert LOGGING['root']['handlers'] == ['console']
    assert 'file' not in LOGGING['handlers']


def test_preview_then_confirm_checks_current_policy(admin_client):
    call_command('configure_maintenance', stdout=StringIO())
    assert submit(admin_client, False).status_code == 400
    response = submit(admin_client)
    assert response.status_code == 202
    identifier = response.json()['data']['id']
    run_maintenance(identifier)
    assert row(admin_client)['preview']['result']['policy']['operation_days'] == 365
    SystemConfig.objects.create(key='lifecycle.operation_days', value=500)
    assert row(admin_client)['preview'] is None
    assert submit(admin_client, False, identifier, 'stale').status_code == 400
    SystemConfig.objects.all().delete()
    response = submit(admin_client, False, identifier, 'execute')
    assert response.status_code == 202
    run_maintenance(response.json()['data']['id'])
    assert TaskRecord.objects.get(pk=response.json()['data']['id']).status == 'success'


def test_preview_does_not_delete_logs_or_source(admin_user):
    log = old(OperationLog.objects.create(user=admin_user, action='update', resource='fixture', ip_address='127.0.0.1'))
    file = source(admin_user)
    result = clean(dry_run=True)
    assert result['eligible']['operation'] == result['eligible']['imports'] == 1
    assert OperationLog.objects.filter(pk=log.pk).exists() and file.file.storage.exists(file.file.name)
    assert result['deleted'] == {'operation': 0, 'login': 0, 'exception': 0, 'imports': 0}


def test_execute_cleans_only_expired_registered_logs_and_sources(admin_user):
    operation = old(OperationLog.objects.create(user=admin_user, action='read', resource='fixture', ip_address='127.0.0.1'))
    login = old(LoginLog.objects.create(username='fixture', status='failed', ip_address='127.0.0.1'))
    exception = old(ExceptionLog.objects.create(level='error', message='fixture', traceback='fixture'))
    file = source(admin_user)
    general = source(admin_user, 'general')
    avatar = source(admin_user, 'avatar')
    recent = source(admin_user, days=1)
    result = clean()
    assert result['deleted'] == {'operation': 1, 'login': 1, 'exception': 1, 'imports': 1}
    assert not OperationLog.objects.filter(pk=operation.pk).exists()
    assert not LoginLog.objects.filter(pk=login.pk).exists()
    assert not ExceptionLog.objects.filter(pk=exception.pk).exists()
    assert not FileModel.objects.filter(pk=file.pk).exists() and not file.file.storage.exists(file.file.name)
    assert FileModel.objects.filter(pk__in=[general.pk, avatar.pk, recent.pk]).count() == 3
    assert OperationLog.objects.filter(resource='lifecycle').count() == 4
    assert TaskRecord.objects.get(related_resource='maintenance:lifecycle').status == 'success'


@pytest.mark.parametrize('status,completed_days', [('pending', 100), ('running', 100), ('failed', None), ('success', 1)])
def test_active_unknown_or_recent_import_protects_source(admin_user, status, completed_days):
    file = source(admin_user)
    TaskRecord.objects.create(name='导入', task_type='import', status=status,
        result={'file_id': str(file.pk)}, completed_at=timezone.now() - timedelta(days=completed_days) if completed_days else None)
    result = clean()
    assert result['protected_imports'] == 1 and result['deleted']['imports'] == 0
    assert FileModel.objects.filter(pk=file.pk).exists()


def test_expired_terminal_import_allows_source_cleanup(admin_user):
    file = source(admin_user)
    task = TaskRecord.objects.create(name='导入', task_type='import', status='failed',
        result={'file_id': str(file.pk)}, completed_at=timezone.now() - timedelta(days=100))
    assert clean()['deleted']['imports'] == 1
    assert TaskRecord.objects.filter(pk=task.pk).exists()


def test_storage_failure_preserves_record_and_reports_partial_result(admin_user):
    file = source(admin_user)
    with patch.object(file.file.storage, 'delete', side_effect=OSError('private endpoint credential')):
        result = clean()
    assert result['failed'] == 1 and result['deleted']['imports'] == 0
    assert FileModel.objects.filter(pk=file.pk).exists()
    assert not OperationLog.objects.filter(resource='lifecycle', description__contains='imports').exists()
    task = TaskRecord.objects.get(related_resource='maintenance:lifecycle')
    assert task.status == 'failed' and task.error == 'lifecycle_partial_failure'
    assert 'private' not in str(task.result)


def test_audit_failure_rolls_back_database_deletion(admin_user):
    log = old(LoginLog.objects.create(username='fixture', status='failed', ip_address='127.0.0.1'))
    with patch('apps.tasks.lifecycle.audit', side_effect=RuntimeError('private')):
        with pytest.raises(RuntimeError):
            clean()
    assert LoginLog.objects.filter(pk=log.pk).exists()
    assert TaskRecord.objects.get().error == 'RuntimeError'


def test_bounded_batches_leave_more_visible(admin_user, monkeypatch):
    import apps.tasks.lifecycle as lifecycle
    monkeypatch.setattr(lifecycle, 'MAX_ROWS', 100)
    LoginLog.objects.bulk_create([LoginLog(username='fixture', status='success', ip_address='127.0.0.1') for _ in range(103)])
    LoginLog.objects.update(created_at=timezone.now() - timedelta(days=400))
    result = clean()
    assert result['deleted']['login'] == 100 and result['more'] and LoginLog.objects.count() == 3
    assert clean()['deleted']['login'] == 3


def test_protected_sources_do_not_starve_later_files(admin_user, monkeypatch):
    import apps.tasks.lifecycle as lifecycle
    monkeypatch.setattr(lifecycle, 'MAX_ROWS', 1)
    protected = source(admin_user, days=500)
    TaskRecord.objects.create(name='导入', task_type='import', status='pending',
        result={'file_id': str(protected.pk)})
    expired = source(admin_user)
    result = clean()
    assert result['deleted']['imports'] == 1 and result['protected_imports'] == 1
    assert FileModel.objects.filter(pk=protected.pk).exists()
    assert not FileModel.objects.filter(pk=expired.pk).exists()


@pytest.mark.parametrize('key,invalid', [('operation', 179), ('login', 29), ('exception', 6), ('import', 0)])
def test_retention_minimum_cannot_be_bypassed(admin_client, key, invalid):
    url = '/api/v1/system/config/lifecycle.' + key + '_days/'
    assert admin_client.patch(url, {'value': invalid, 'version': 0}, format='json').status_code == 400
    assert admin_client.patch(url, {'value': 3651, 'version': 0}, format='json').status_code == 400


def test_policy_read_failure_finishes_task_without_private_error():
    with patch('apps.tasks.lifecycle.policy', side_effect=RuntimeError('private endpoint')):
        with pytest.raises(RuntimeError):
            clean()
    assert TaskRecord.objects.get().status == 'failed'
    assert TaskRecord.objects.get().error == 'RuntimeError'


def test_policy_change_rejected_before_any_deletion():
    expected = policy()
    SystemConfig.objects.create(key='lifecycle.login_days', value=365)
    with pytest.raises(ValueError, match='preview_policy_changed'):
        clean(expected_policy=expected)


def test_module_off_skips_import_cleanup_and_celery_entry(settings, admin_user):
    file = source(admin_user)
    settings.ADMINCORE_MODULES = ()
    assert clean()['deleted']['imports'] == 0 and FileModel.objects.filter(pk=file.pk).exists()
    from celery.exceptions import Ignore
    with pytest.raises(Ignore):
        cleanup_lifecycle()


def test_cli_default_preview_and_explicit_confirmation():
    output = StringIO()
    call_command('cleanup_history', stdout=output)
    assert '"dry_run": true' in output.getvalue()
    with pytest.raises(CommandError):
        call_command('cleanup_history', execute=True, stdout=StringIO())
    call_command('cleanup_history', execute=True, confirm='执行清理', stdout=StringIO())


def test_expired_import_retry_is_clear_and_creates_no_task(admin_client, admin_user):
    file = source(admin_user)
    task = TaskRecord.objects.create(name='导入', task_type='import', status='failed', related_resource='users',
        creator=admin_user, result={'file_id': str(file.pk)}, completed_at=timezone.now() - timedelta(days=100))
    clean()
    before = TaskRecord.objects.count()
    response = admin_client.post(f'/api/v1/data-io/import/{task.pk}/', {}, format='json')
    assert response.status_code == 400 and '已过期或不可用' in response.json()['message']
    assert TaskRecord.objects.count() == before
