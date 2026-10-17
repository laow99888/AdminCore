"""事务接续、任务策略和脱敏失败告警；真实并发另由 PostgreSQL 验收。"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone

from apps.core.models import OutboxEvent, SystemConfig
from apps.core.tasks import dispatch_outbox
from apps.data_io.tasks import run_data_import
from apps.tasks.models import ImportExecution, ImportRowReceipt, TaskRecord
from apps.tasks.reliability import deliver_failure, recover_lost_imports
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db
User = get_user_model()


def submit(client, rows=b'first,a@example.com\nsecond,b@example.com\n'):
    response = client.post('/api/v1/data-io/import/', {'resource': 'users',
        'file': SimpleUploadedFile('users.csv', b'username,email\n' + rows)}, format='multipart', HTTP_X_REQUEST_ID='task-origin-test')
    assert response.status_code == 200, response.json()
    return TaskRecord.objects.get(pk=response.json()['data']['id'])


def test_submission_snapshots_policy_and_binds_device(admin_client, admin_user):
    SystemConfig.objects.create(key='tasks.import_timeout', value=90)
    record = submit(admin_client)
    execution = record.import_execution
    assert execution.policy['soft_timeout'] == 90 and execution.policy['hard_timeout'] == 120
    assert execution.session_id and execution.request_id == 'task-origin-test'
    assert OutboxEvent.objects.get(topic='import.requested').request_id == 'task-origin-test'
    SystemConfig.objects.filter(key='tasks.import_timeout').update(value=600)
    assert execution.policy['soft_timeout'] == 90
    with patch.object(run_data_import, 'apply_async') as publish:
        dispatch_outbox()
    assert publish.call_args.kwargs['soft_time_limit'] == 90
    assert publish.call_args.kwargs['time_limit'] == 120


def test_duplicate_delivery_and_success_replay_are_blocked(admin_client):
    record = submit(admin_client)
    run_data_import(str(record.pk))
    assert run_data_import(str(record.pk)) == {'skipped': True}
    assert User.objects.filter(username__in=['first', 'second']).count() == 2
    assert ImportRowReceipt.objects.count() == 2
    assert admin_client.post(f'/api/v1/tasks/{record.pk}/resume/').status_code == 409


@pytest.mark.parametrize('debug', [True, False])
def test_import_broker_failure_never_falls_back_to_synchronous_writes(admin_client, settings, debug):
    settings.DEBUG = debug
    record = submit(admin_client)
    with patch.object(run_data_import, 'apply_async', side_effect=ConnectionError('private-broker-address')), \
            patch.object(run_data_import, 'run') as synchronous:
        assert dispatch_outbox() == {'processed': 0, 'failed': 1}
        synchronous.assert_not_called()
    record.refresh_from_db()
    event = OutboxEvent.objects.get(topic='import.requested')
    assert record.status == 'pending' and event.status == 'failed'
    assert event.last_error == 'ConnectionError'
    assert not User.objects.filter(username__in=['first', 'second']).exists()
    assert not record.import_execution.batch.receipts.exists()
    OutboxEvent.objects.filter(pk=event.pk).update(available_at=timezone.now() - timedelta(seconds=1))
    with patch.object(run_data_import, 'apply_async') as publish:
        assert dispatch_outbox() == {'processed': 1, 'failed': 0}
        assert publish.call_args.kwargs['task_id'] == record.celery_task_id == str(record.pk)
    run_data_import(str(record.pk))
    assert run_data_import(str(record.pk)) == {'skipped': True}
    assert User.objects.filter(username__in=['first', 'second']).count() == 2
    assert record.import_execution.batch.receipts.count() == 2


def test_cancel_after_committed_row_resumes_only_remaining(admin_client):
    record = submit(admin_client)
    from apps.data_io.resources import get_resource
    original = get_resource('users')['create_row']
    def create_then_cancel(data):
        obj, error = original(data)
        TaskRecord.objects.filter(pk=record.pk).update(status='cancelled', completed_at=timezone.now())
        return obj, error
    with patch('apps.data_io.resources.create_user_row', create_then_cancel):
        # 注册表保留函数引用，显式复制完整资源定义。
        config = dict(get_resource('users'), create_row=create_then_cancel)
        with patch('apps.data_io.tasks.get_resource', create=True):
            with patch('apps.data_io.resources.get_resource', return_value=config):
                run_data_import(str(record.pk))
    assert User.objects.filter(username='first').exists() and not User.objects.filter(username='second').exists()
    assert ImportRowReceipt.objects.count() == 1
    response = admin_client.post(f'/api/v1/tasks/{record.pk}/resume/')
    assert response.status_code == 202, response.json()
    new = TaskRecord.objects.get(pk=response.json()['data']['id'])
    assert new.import_execution.attempt == 2
    assert admin_client.post(f'/api/v1/tasks/{record.pk}/resume/').status_code == 409
    run_data_import(str(new.pk))
    new.refresh_from_db()
    assert new.status == 'success' and new.result['created'] == 2
    assert ImportRowReceipt.objects.count() == 2


def test_exception_row_rolls_back_and_resume_does_not_duplicate(admin_client):
    record = submit(admin_client)
    from apps.data_io.resources import get_resource
    config = get_resource('users')
    original = config['create_row']
    def interrupt(data):
        obj, error = original(data)
        if data['username'] == 'second':
            raise RuntimeError('private import contents')
        return obj, error
    with patch.dict(config, create_row=interrupt):
        with pytest.raises(RuntimeError):
            run_data_import(str(record.pk))
    record.refresh_from_db()
    assert record.error == 'RuntimeError' and record.result['created'] == 1
    assert not User.objects.filter(username='second').exists()
    response = admin_client.post(f'/api/v1/tasks/{record.pk}/resume/')
    run_data_import(response.json()['data']['id'])
    assert User.objects.filter(username__in=['first', 'second']).count() == 2
    assert ImportRowReceipt.objects.count() == 2


def test_device_revoked_before_execution_blocks_import(admin_client):
    record = submit(admin_client)
    from apps.auth_app.models import AuthSession
    AuthSession.objects.filter(pk=record.import_execution.session_id).update(revoked_at=timezone.now())
    run_data_import(str(record.pk))
    record.refresh_from_db()
    assert record.status == 'failed' and record.error == 'execution_not_authorized'
    assert not ImportRowReceipt.objects.exists()


def test_digest_changed_and_limit_rejected_without_writes(admin_client):
    record = submit(admin_client)
    execution = record.import_execution
    execution.batch.source_sha256 = '0' * 64
    execution.batch.save()
    run_data_import(str(record.pk))
    record.refresh_from_db()
    assert record.error == 'import_source_changed' and not ImportRowReceipt.objects.exists()
    large = submit(admin_client, b'x,x@example.com\n' * 5001)
    run_data_import(str(large.pk))
    large.refresh_from_db()
    assert large.error == 'import_row_limit_5000' and not ImportRowReceipt.objects.exists()


def test_lost_execution_stops_without_automatic_replay(admin_client):
    record = submit(admin_client)
    TaskRecord.objects.filter(pk=record.pk).update(status='running', started_at=timezone.now() - timedelta(hours=1))
    recover_lost_imports()
    record.refresh_from_db()
    assert record.status == 'failed' and record.error == 'worker_lost_committed_rows_preserved'
    assert not User.objects.filter(username='first').exists()


@pytest.mark.parametrize('terminal', ['cancel', 'worker_lost'])
def test_terminal_import_summary_uses_committed_receipts(admin_client, terminal):
    record = submit(admin_client)
    TaskRecord.objects.filter(pk=record.pk).update(status='running',
        started_at=timezone.now() - timedelta(hours=1),
        result={'file_id': str(record.import_execution.batch.source_id), 'total': 100, 'created': 1})
    ImportRowReceipt.objects.bulk_create([
        ImportRowReceipt(batch=record.import_execution.batch, row=2, created=True),
        ImportRowReceipt(batch=record.import_execution.batch, row=3, created=True),
        ImportRowReceipt(batch=record.import_execution.batch, row=4, created=False, error='row_validation_failed'),
    ])
    if terminal == 'cancel':
        with patch('config.celery.app.control.revoke'):
            response = admin_client.post(f'/api/v1/tasks/{record.pk}/cancel/')
        assert response.status_code == 200, response.json()
    else:
        recover_lost_imports()
    record.refresh_from_db()
    assert record.status == ('cancelled' if terminal == 'cancel' else 'failed')
    assert record.result['created'] == 2 and record.result['failed'] == 1
    assert record.result['processed'] == 3 and record.result['total'] == 100
    assert record.result['errors'] == [{'row': 4, 'message': 'row_validation_failed'}]


def test_dispatch_exhaustion_is_terminal_but_manual_resume_is_allowed(admin_client):
    record = submit(admin_client)
    OutboxEvent.objects.filter(topic='import.requested').update(attempts=5)
    with patch.object(run_data_import, 'apply_async') as publish:
        dispatch_outbox()
    assert not publish.called
    record.refresh_from_db()
    assert record.error == 'dispatch_attempts_exhausted'
    event = OutboxEvent.objects.get(topic='import.requested')
    assert event.last_error == 'dispatch_exhausted'
    assert admin_client.post(f'/api/v1/reliability/events/{event.pk}/retry/').status_code == 409
    assert admin_client.post(f'/api/v1/tasks/{record.pk}/resume/').status_code == 202


def test_failures_atomic_deduplicated_private_and_current_scope(admin_client, member_user):
    record = submit(admin_client)
    assert record.mark_failed('RuntimeError')
    assert not record.mark_failed('changed')
    event = OutboxEvent.objects.get(topic='task.failed')
    assert event.payload == {'record_id': str(record.pk)}
    assert event.request_id == 'task-origin-test'
    deliver_failure(event.payload)
    deliver_failure(event.payload)
    assert Notification.objects.filter(notification_type='task').count() == 1
    assert not Notification.objects.filter(recipient=member_user).exists()
    note = Notification.objects.get(notification_type='task')
    assert 'RuntimeError' not in note.content and 'a@example.com' not in note.content


def test_failure_rollback_and_module_disable_create_no_alert(admin_user, settings):
    record = TaskRecord.objects.create(name='private', creator=admin_user)
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            record.mark_failed('RuntimeError')
            raise RuntimeError()
    assert not OutboxEvent.objects.exists()
    settings.ADMINCORE_MODULES = ()
    record.mark_failed('RuntimeError')
    assert not OutboxEvent.objects.exists()


@pytest.mark.parametrize('value', [0, 1801, True, '90'])
def test_policy_parameters_are_bounded(admin_client, value):
    assert admin_client.patch('/api/v1/system/config/tasks.import_timeout/', {'value': value, 'version': 0}, format='json').status_code == 400


def test_fifth_execution_cannot_resume(admin_client):
    record = submit(admin_client)
    ImportExecution.objects.filter(pk=record.pk).update(attempt=5)
    record.mark_cancelled()
    assert admin_client.post(f'/api/v1/tasks/{record.pk}/resume/').status_code == 400


def test_finished_record_cannot_be_resurrected(admin_user):
    record = TaskRecord.objects.create(name='state', creator=admin_user)
    record.mark_success({})
    assert not record.mark_started()
    assert not record.mark_failed('RuntimeError')
    assert record.status == 'success'


def test_periodic_publish_route_uses_registered_timeout_only():
    from apps.tasks.routing import registered_policy
    SystemConfig.objects.create(key='tasks.maintenance_timeout', value=120)
    assert registered_policy('tasks.cleanup_lifecycle', (), {}, {}) == {'soft_time_limit': 120, 'time_limit': 150}
    assert registered_policy('tasks.request_backup', (), {}, {}) is None
    assert registered_policy('unregistered.shell', (), {}, {}) is None
    from apps.tasks.tasks import cleanup_expired_notifications
    with patch('celery.Task.apply_async') as publish:
        cleanup_expired_notifications.apply_async(kwargs={'dry_run': True})
        assert publish.call_args.kwargs['soft_time_limit'] == 120
        assert publish.call_args.kwargs['time_limit'] == 150
        cleanup_expired_notifications.apply_async(kwargs={'dry_run': True}, soft_time_limit=90, time_limit=120)
        assert publish.call_args.kwargs['soft_time_limit'] == 90
