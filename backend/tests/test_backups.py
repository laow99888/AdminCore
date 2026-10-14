"""受限宿主备份协议、计划与任务状态，不读取部署凭据或执行 Docker。"""
from datetime import timedelta
from io import StringIO
import json
import uuid
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django_celery_beat.models import PeriodicTask

from apps.notifications.models import Notification
from apps.tasks.backup import claim, complete, recover_lost, validate_result
from apps.tasks.models import BackupRequest, TaskRecord
from apps.tasks.tasks import request_backup, run_maintenance

pytestmark = pytest.mark.django_db
BASE = '/api/v1/tasks/schedules/'


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.ADMINCORE_BACKUP_ENABLED = True
    call_command('configure_maintenance', stdout=StringIO())


def current(client):
    return next(row for row in client.get(BASE).json()['data'] if row['key'] == 'backup')


def submit(client, dry_run=False, idem='backup', confirmation='执行备份'):
    return client.post(BASE + 'backup/run/', {'revision': current(client)['revision'],
        'options': {'dry_run': dry_run}, 'confirmation': confirmation}, format='json', HTTP_IDEMPOTENCY_KEY=idem)


def result():
    stamp = '20261014-010203'
    return {'timestamp': stamp, 'artifacts': [
        {'name': f'admincore-db-{stamp}.dump', 'sha256': 'a' * 64, 'bytes': 128},
        {'name': f'admincore-media-{stamp}.tar.gz', 'sha256': 'b' * 64, 'bytes': 45},
        {'name': f'admincore-{stamp}.sha256', 'sha256': 'c' * 64, 'bytes': 200}],
        'remote_copy': True, 'pruned_sets': 0, 'retention_warning': False}


def test_plan_disabled_by_default_preserves_changes(admin_client):
    row = current(admin_client)
    assert not row['enabled'] and not row['requires_preview'] and row['confirmation'] == '执行备份'
    assert row['cron']['minute'] == '0' and row['cron']['hour'] == '2'
    payload = {'revision': row['revision'], 'enabled': True, **row['cron'], 'options': {}}
    assert admin_client.patch(BASE + 'backup/', payload, format='json').status_code == 200
    call_command('configure_maintenance', stdout=StringIO())
    assert current(admin_client)['enabled']


def test_task_queue_uniqueness_and_claim_token():
    queued = request_backup()
    assert queued['queued'] and request_backup()['reason'] == 'already_pending'
    first = claim()
    assert first['record_id'] == queued['record_id'] and first['retention_days'] == 30
    assert first['retention_count'] == 7 and uuid.UUID(first['token'])
    assert claim() is None
    with pytest.raises(ValueError):
        complete(first['record_id'], uuid.uuid4(), result=result())
    complete(first['record_id'], first['token'], result=result())
    record = TaskRecord.objects.get(pk=first['record_id'])
    assert record.status == 'success' and record.result == result() and record.progress == 100
    with pytest.raises(ValueError):
        complete(first['record_id'], first['token'], result=result())
    assert request_backup()['queued']


def test_manual_confirm_idempotent_preview_no_host_queue(admin_client, member_client):
    assert member_client.get(BASE).status_code == 403
    assert submit(admin_client, confirmation='执行清理').status_code == 400
    preview = submit(admin_client, dry_run=True, idem='preview')
    assert preview.status_code == 202
    run_maintenance(preview.json()['data']['id'])
    assert not BackupRequest.objects.exists()
    assert TaskRecord.objects.get().result['dry_run']
    assert TaskRecord.objects.get().result['requires_host_runner']
    assert TaskRecord.objects.get().result['consistency'] == 'stop_writers'
    visible = current(admin_client)['preview']
    assert visible['id'] == preview.json()['data']['id']
    assert visible['result']['retention_count'] == 7
    actual = submit(admin_client)
    assert actual.status_code == 202
    assert submit(admin_client).headers['Idempotency-Replayed'] == 'true'
    assert submit(admin_client, idem='other').status_code == 400
    run_maintenance(actual.json()['data']['id'])
    assert claim()['record_id'] == actual.json()['data']['id']


def test_pending_cancel_running_rejected(admin_client):
    response = submit(admin_client)
    identifier = response.json()['data']['id']
    run_maintenance(identifier)
    assert admin_client.post(f'/api/v1/tasks/{identifier}/cancel/').status_code == 200
    assert claim() is None
    queued = request_backup()
    claim()
    assert admin_client.post(f"/api/v1/tasks/{queued['record_id']}/cancel/").status_code == 409


def test_disabled_gate_previews_still_available(admin_client, settings):
    settings.ADMINCORE_BACKUP_ENABLED = False
    assert request_backup()['reason'] == 'backup_disabled'
    assert submit(admin_client).status_code == 400
    assert submit(admin_client, dry_run=True).status_code == 202
    assert claim() is None
    assert not BackupRequest.objects.exists()


def test_module_and_auth_rechecked_at_host_claim(admin_client, admin_user, settings):
    response = submit(admin_client)
    run_maintenance(response.json()['data']['id'])
    settings.ADMINCORE_MODULES = ()
    assert claim() is None
    settings.ADMINCORE_MODULES = ('tasks', 'notifications')
    admin_user.session_version += 1
    admin_user.save()
    assert claim() is None
    assert TaskRecord.objects.get().error == 'backup_disabled'


def test_manual_identity_rechecked_after_queueing(admin_client, admin_user):
    response = submit(admin_client)
    run_maintenance(response.json()['data']['id'])
    admin_user.session_version += 1
    admin_user.save()
    assert claim() is None
    assert TaskRecord.objects.get().error == 'execution_not_authorized'


def test_failure_dedup_and_lost_not_replayed(admin_user, member_user):
    queued = request_backup()
    claimed = claim()
    BackupRequest.objects.filter(pk=queued['record_id']).update(claimed_at=timezone.now() - timedelta(hours=3))
    recover_lost()
    recover_lost()
    record = TaskRecord.objects.get()
    assert record.status == 'failed' and record.error == 'result_unknown'
    assert Notification.objects.filter(recipient=admin_user).count() == 1
    assert not Notification.objects.filter(recipient=member_user).exists()
    with pytest.raises(ValueError):
        complete(claimed['record_id'], claimed['token'], result=result())
    assert claim() is None


@pytest.mark.parametrize('change', [
    {'timestamp': '../../x'}, {'timestamp': '20260231-010203'}, {'artifacts': []},
    {'remote_copy': 1}, {'retention_warning': 'false'}, {'pruned_sets': True},
    {'pruned_sets': -1}, {'token': 'secret'},
])
def test_strict_results(change):
    with pytest.raises(ValueError):
        validate_result({**result(), **change})


@pytest.mark.parametrize('field,value', [('name', '../dump'), ('sha256', 'secret'), ('bytes', True), ('bytes', -1)])
def test_artifact_metadata_strict(field, value):
    data = result()
    data['artifacts'][0][field] = value
    with pytest.raises(ValueError):
        validate_result(data)


def test_cli_stdout_json_finish_and_safe_failure(admin_user):
    request_backup()
    output = StringIO()
    call_command('backup_queue', 'claim', stdout=output)
    claimed = json.loads(output.getvalue())
    with patch('sys.stdin', StringIO(json.dumps(result()))):
        call_command('backup_queue', 'finish', claimed['record_id'], token=uuid.UUID(claimed['token']), stdout=StringIO())
    request_backup()
    second = claim()
    call_command('backup_queue', 'fail', second['record_id'], token=uuid.UUID(second['token']), code='backup_failed', stdout=StringIO())
    assert TaskRecord.objects.get(pk=second['record_id']).error == 'backup_failed'
    assert Notification.objects.count() == 1
    with patch('sys.stdin', StringIO('{"password":"secret"}')):
        with pytest.raises(CommandError) as exc:
            call_command('backup_queue', 'finish', second['record_id'], token=uuid.UUID(second['token']))
    assert 'secret' not in str(exc.value)


def test_database_unfinished_constraint():
    request_backup()
    with pytest.raises(IntegrityError), transaction.atomic():
        TaskRecord.objects.create(name='duplicate', task_type='backup', related_resource='maintenance:backup')


def test_bad_persisted_policy_fails_closed():
    request_backup()
    BackupRequest.objects.update(options={'retention_days': -1, 'retention_count': 0, 'secret': 'private'})
    assert claim() is None
    assert TaskRecord.objects.get().error == 'backup_failed'


def test_duplicate_json_keys_and_oversized_results_rejected():
    request_backup()
    claimed = claim()
    for payload in ['{"timestamp":"20261014-010203","timestamp":"20261014-010203"}', ' ' * 16385]:
        with patch('sys.stdin', StringIO(payload)), pytest.raises(CommandError):
            call_command('backup_queue', 'finish', claimed['record_id'], token=uuid.UUID(claimed['token']))
    assert TaskRecord.objects.get().status == 'running'


def test_pending_lease_expiry_and_disabled_gate_free_queue(admin_user, settings):
    queued = request_backup()
    TaskRecord.objects.filter(pk=queued['record_id']).update(created_at=timezone.now() - timedelta(hours=3))
    assert claim() is None
    assert TaskRecord.objects.get(pk=queued['record_id']).error == 'runner_unavailable'
    assert Notification.objects.count() == 1
    next_request = request_backup()
    settings.ADMINCORE_BACKUP_ENABLED = False
    assert claim() is None
    assert TaskRecord.objects.get(pk=next_request['record_id']).error == 'backup_disabled'
    settings.ADMINCORE_BACKUP_ENABLED = True
    assert request_backup()['queued']


def test_dispatch_recovers_pending_even_when_tasks_module_off(settings):
    from apps.core.tasks import dispatch_outbox
    queued = request_backup()
    settings.ADMINCORE_MODULES = ()
    dispatch_outbox()
    assert TaskRecord.objects.get(pk=queued['record_id']).error == 'backup_disabled'
