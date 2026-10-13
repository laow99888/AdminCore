"""注册维护计划、可靠提交与真实任务执行的安全边界。"""
from contextlib import contextmanager
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from django_celery_beat.models import PeriodicTask

from apps.core.models import OutboxEvent, SystemConfig
from apps.core.tasks import dispatch_outbox
from apps.logs.models import OperationLog
from apps.notifications.models import Notification
from apps.tasks.models import MaintenanceRequest, TaskRecord
from apps.tasks.tasks import run_maintenance, recover_lost_maintenance

pytestmark = pytest.mark.django_db
BASE = '/api/v1/tasks/schedules/'


@pytest.fixture(autouse=True)
def plans():
    call_command('configure_maintenance', stdout=StringIO())


def row(client, key='notifications'):
    return next(item for item in client.get(BASE).json()['data'] if item['key'] == key)


def change(client, key='notifications', **updates):
    current = row(client, key)
    payload = {'revision': current['revision'], 'enabled': current['enabled'],
               **current['cron'], 'options': current['options'], **updates}
    return client.patch(BASE + key + '/', payload, format='json')


def submit(client, dry_run=True, key='notifications', idem='fixture-preview', preview_id=None, **extra):
    current = row(client, key)
    payload = {'revision': current['revision'], 'options': {'dry_run': dry_run},
               'preview_id': preview_id, 'confirmation': '' if dry_run else '执行清理', **extra}
    return client.post(BASE + key + '/run/', payload, format='json', HTTP_IDEMPOTENCY_KEY=idem)


def preview(client):
    response = submit(client)
    assert response.status_code == 202, response.json()
    identifier = response.json()['data']['id']
    run_maintenance(identifier)
    return identifier


def test_schedule_whitelist_and_permissions(admin_client, member_client):
    assert member_client.get(BASE).status_code == 403
    assert len(admin_client.get(BASE).json()['data']) == 2
    assert admin_client.patch(BASE + 'core.dispatch_outbox/', {}, format='json').status_code == 404
    assert member_client.post(BASE + 'files/run/', {}, format='json').status_code == 403


def test_update_version_audit_and_bootstrap_preservation(admin_client):
    current = row(admin_client)
    response = change(admin_client, enabled=False, minute='*/15', hour='*', timezone='UTC')
    assert response.status_code == 200
    assert response.json()['data']['cron']['timezone'] == 'UTC'
    stale = admin_client.patch(BASE + 'notifications/', {'revision': current['revision'],
        'enabled': True, **current['cron'], 'options': {}}, format='json')
    assert stale.status_code == 409
    call_command('configure_maintenance', stdout=StringIO())
    assert not row(admin_client)['enabled']
    assert OperationLog.objects.filter(resource='maintenance_schedule').count() == 1


@pytest.mark.parametrize('updates', [
    {'minute': '60'}, {'hour': '24'}, {'minute': '*/0'}, {'day_of_month': '32'},
    {'month_of_year': '13'}, {'day_of_week': '7'}, {'timezone': 'Mars/Unknown'},
    {'minute': 'exec()'}, {'task': 'os.system'}, {'enabled': 'true'},
    {'options': {'command': 'shell'}}, {'options': {'dry_run': 'false'}}, {'options': []},
])
def test_invalid_schedule_rejected_without_writes(admin_client, updates):
    before = row(admin_client)['revision']
    assert change(admin_client, **updates).status_code == 400
    assert row(admin_client)['revision'] == before
    assert not OperationLog.objects.filter(resource='maintenance_schedule').exists()


@pytest.mark.parametrize('batch', [0, 101, True, '10', 1.5])
def test_batch_size_strict(admin_client, batch):
    assert change(admin_client, key='files', options={'batch_size': batch}).status_code == 400


def test_manual_preview_is_reliable_idempotent_and_does_not_delete(admin_client, member_user):
    note = Notification.objects.create(recipient=member_user, title='过期', is_read=True)
    Notification.objects.filter(pk=note.pk).update(read_at=timezone.now() - timedelta(days=100))
    first = submit(admin_client)
    assert first.status_code == 202
    identifier = first.json()['data']['id']
    repeat = submit(admin_client)
    assert repeat.status_code == 202 and repeat.headers['Idempotency-Replayed'] == 'true'
    assert TaskRecord.objects.count() == MaintenanceRequest.objects.count() == 1
    assert OutboxEvent.objects.get().topic == 'maintenance.requested'
    result = run_maintenance(identifier)
    assert result['eligible_notifications'] == 1 and Notification.objects.filter(pk=note.pk).exists()
    assert row(admin_client)['preview']['id'] == identifier
    assert run_maintenance(identifier)['reason'] == 'already_claimed'


def test_execute_requires_recent_own_preview_confirmation_and_policy(admin_client, member_user):
    assert submit(admin_client, dry_run=False).status_code == 400
    identifier = preview(admin_client)
    assert submit(admin_client, False, idem='bad-confirm', preview_id=identifier, confirmation='yes').status_code == 400
    SystemConfig.objects.create(key='notifications.retention_days', value=120)
    assert submit(admin_client, False, idem='policy', preview_id=identifier).status_code == 400
    SystemConfig.objects.all().delete()
    note = Notification.objects.create(recipient=member_user, title='过期', is_read=True)
    Notification.objects.filter(pk=note.pk).update(read_at=timezone.now() - timedelta(days=100))
    accepted = submit(admin_client, False, idem='execute', preview_id=identifier)
    assert accepted.status_code == 202
    result = run_maintenance(accepted.json()['data']['id'])
    assert result['deleted_notifications'] == 1 and not Notification.objects.filter(pk=note.pk).exists()


def test_expired_preview_rejected_at_submission_and_worker(admin_client):
    identifier = preview(admin_client)
    response = submit(admin_client, False, idem='execute', preview_id=identifier)
    assert response.status_code == 202
    TaskRecord.objects.filter(pk=identifier).update(completed_at=timezone.now() - timedelta(minutes=16))
    assert submit(admin_client, False, idem='expired', preview_id=identifier).status_code == 400
    run_maintenance(response.json()['data']['id'])
    assert TaskRecord.objects.get(pk=response.json()['data']['id']).error == 'preview_expired_or_policy_changed'


@pytest.mark.parametrize('field,value', [('is_active', False), ('is_staff', False), ('must_change_password', True), ('session_version', 5)])
def test_worker_rechecks_identity(admin_client, admin_user, field, value):
    response = submit(admin_client)
    setattr(admin_user, field, value)
    if field == 'is_staff':
        admin_user.is_superuser = False
    admin_user.save()
    run_maintenance(response.json()['data']['id'])
    assert TaskRecord.objects.get().status == 'failed'
    assert TaskRecord.objects.get().error == 'execution_not_authorized'


def test_worker_module_off_and_queue_expiry(admin_client, settings):
    response = submit(admin_client)
    settings.ADMINCORE_MODULES = ('tasks',)
    run_maintenance(response.json()['data']['id'])
    assert TaskRecord.objects.get().error == 'execution_not_authorized'
    settings.ADMINCORE_MODULES = ('tasks', 'notifications', 'files')
    other = submit(admin_client, idem='old')
    TaskRecord.objects.filter(pk=other.json()['data']['id']).update(created_at=timezone.now() - timedelta(hours=25))
    run_maintenance(other.json()['data']['id'])
    assert TaskRecord.objects.get(pk=other.json()['data']['id']).error == 'request_expired'


def test_broker_failure_outbox_retry_keeps_registered_request(admin_client):
    response = submit(admin_client)
    with patch('apps.tasks.tasks.run_maintenance.apply_async', side_effect=RuntimeError('private broker secret')):
        assert dispatch_outbox()['failed'] == 1
    event = OutboxEvent.objects.get()
    assert event.status == 'failed' and event.last_error == 'RuntimeError'
    assert TaskRecord.objects.get().status == 'pending'
    OutboxEvent.objects.filter(pk=event.pk).update(available_at=timezone.now())
    with patch('apps.tasks.tasks.run_maintenance.apply_async') as publish:
        assert dispatch_outbox()['processed'] == 1
        assert publish.call_args.kwargs['task_id'] == response.json()['data']['id']


def test_pending_cancel_is_final_but_running_cannot_be_cancelled(admin_client):
    response = submit(admin_client)
    identifier = response.json()['data']['id']
    assert admin_client.post(f'/api/v1/tasks/{identifier}/cancel/').status_code == 200
    assert OperationLog.objects.filter(resource='maintenance_run', resource_id=identifier, action='update').exists()
    assert run_maintenance(identifier)['reason'] == 'already_claimed'
    TaskRecord.objects.filter(pk=identifier).update(status='running', started_at=timezone.now())
    assert admin_client.post(f'/api/v1/tasks/{identifier}/cancel/').status_code == 409
    assert TaskRecord.objects.get().status == 'running'


def test_overlap_records_skip_and_lost_execution_is_not_replayed(admin_client):
    identifier = submit(admin_client).json()['data']['id']
    @contextmanager
    def busy(_key):
        yield False
    with patch('apps.tasks.maintenance.maintenance_lock', busy):
        assert run_maintenance(identifier) == {'skipped': True, 'reason': 'overlap'}
    assert TaskRecord.objects.get().status == 'success'
    TaskRecord.objects.filter(pk=identifier).update(status='running', started_at=timezone.now() - timedelta(minutes=11))
    recover_lost_maintenance()
    assert TaskRecord.objects.get().error == 'worker_lost_result_unknown'
    assert run_maintenance(identifier)['reason'] == 'already_claimed'


def test_manual_missing_key_disabled_dispatch_and_non_object_body(admin_client):
    assert admin_client.post(BASE + 'files/run/', {'revision': row(admin_client, 'files')['revision'], 'options': {'dry_run': True}}, format='json').status_code == 400
    assert admin_client.patch(BASE + 'files/', [], format='json').status_code == 400
    PeriodicTask.objects.filter(task='core.dispatch_outbox').update(enabled=False)
    assert submit(admin_client).status_code == 400


def test_unrecognized_existing_kwargs_are_not_exposed_or_logged(admin_client):
    task = PeriodicTask.objects.get(task='tasks.cleanup_expired_notifications')
    task.kwargs = '{"token":"private credential"}'
    task.save()
    current = row(admin_client)
    assert not current['supported'] and current['options'] == {}
    assert change(admin_client).status_code == 400
    assert not OperationLog.objects.filter(description__contains='private credential').exists()
