"""恢复入口的确认、权限撤销、目录变化和全局队列边界。"""
from datetime import timedelta
import copy
import uuid

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.tasks.backup import claim_restore, finish_restore, runner_heartbeat
from apps.tasks.models import BackupPreflight, BackupRestoreRequest, BackupRunnerStatus

pytestmark = pytest.mark.django_db
BASE = '/api/v1/tasks/backups/'
STAMP = '20261016-010203'


@pytest.fixture
def catalog(settings):
    settings.ADMINCORE_BACKUP_ENABLED = True
    payload = {'state': 'idle', 'directory_label': 'backups', 'stage': '', 'last_error': '',
        'artifacts': [{'timestamp': STAMP, 'created_at': '2026-10-16T01:02:03+00:00', 'remote_copy': False,
            'artifacts': [{'name': name, 'sha256': char * 64, 'bytes': 100} for name, char in [
                (f'admincore-db-{STAMP}.dump', 'a'), (f'admincore-media-{STAMP}.tar.gz', 'b'),
                (f'admincore-{STAMP}.sha256', 'c')]]}]}
    runner_heartbeat(payload)
    return payload


def preflight(client):
    response = client.post(BASE + STAMP + '/preflight/', {}, format='json')
    assert response.status_code == 200, response.data
    return response.data['data']['preflight_id']


def restore(client, identifier, **changes):
    return client.post(BASE + STAMP + '/restore/', {'preflight_id': identifier,
        'confirmation': '恢复备份', 'current_password': 'Admin#12345', **changes}, format='json')


def test_status_permissions_staleness_no_cache(admin_client, member_client, catalog):
    assert member_client.get(BASE).status_code == 403
    response = admin_client.get(BASE)
    assert response.status_code == 200 and response.data['data']['state'] == 'idle'
    assert 'no-store' in response['Cache-Control']
    BackupRunnerStatus.objects.update(last_seen_at=timezone.now() - timedelta(minutes=4))
    assert admin_client.get(BASE).data['data']['state'] == 'offline'
    assert admin_client.post(BASE + STAMP + '/preflight/').status_code == 400


def test_confirmation_single_use_and_host_claim(admin_client, catalog):
    identifier = preflight(admin_client)
    assert restore(admin_client, identifier, confirmation='yes').status_code == 400
    assert restore(admin_client, identifier, current_password='incorrect').status_code == 403
    response = restore(admin_client, identifier)
    assert response.status_code == 202, response.data
    claimed = claim_restore()
    assert claimed['request_id'] == response.data['data']['id']
    assert claim_restore() is None
    finish_restore(claimed['request_id'], 'failed', 'fixture_failure')
    assert restore(admin_client, identifier).status_code == 400
    assert admin_client.get(BASE + 'restore-requests/' + claimed['request_id'] + '/').data['data']['status'] == 'failed'


@pytest.mark.parametrize('change', ['expiry', 'digest', 'actor', 'disabled'])
def test_invalid_preflight_refused(admin_client, member_user, catalog, settings, change):
    identifier = preflight(admin_client)
    if change == 'expiry':
        BackupPreflight.objects.filter(pk=identifier).update(expires_at=timezone.now() - timedelta(seconds=1))
    elif change == 'actor':
        BackupPreflight.objects.filter(pk=identifier).update(actor=member_user)
    elif change == 'digest':
        payload = copy.deepcopy(catalog)
        payload['artifacts'][0]['artifacts'][0]['sha256'] = 'd' * 64
        runner_heartbeat(payload)
    else:
        settings.ADMINCORE_BACKUP_ENABLED = False
    assert restore(admin_client, identifier).status_code == 400
    assert not BackupRestoreRequest.objects.exists()


def test_queued_revoke_prevents_execution(admin_client, admin_user, catalog):
    assert restore(admin_client, preflight(admin_client)).status_code == 202
    admin_user.session_version += 1
    admin_user.save()
    assert claim_restore() is None
    assert BackupRestoreRequest.objects.get().error == 'execution_not_authorized'


def test_device_revocation_prevents_host_execution(admin_client, catalog):
    from apps.auth_app.models import AuthSession
    assert restore(admin_client, preflight(admin_client)).status_code == 202
    AuthSession.objects.update(revoked_at=timezone.now())
    assert claim_restore() is None


def test_restore_audit_excludes_password(admin_client, catalog):
    from apps.logs.models import OperationLog
    assert restore(admin_client, preflight(admin_client)).status_code == 202
    log = OperationLog.objects.get(resource='backup_restore', audit_version=1)
    assert log.after_values['timestamp'] == STAMP
    assert 'Admin#12345' not in str(log.after_values) + log.description


def test_global_active_constraint_and_second_request(admin_client, catalog):
    assert restore(admin_client, preflight(admin_client)).status_code == 202
    assert restore(admin_client, preflight(admin_client)).status_code == 400
    with pytest.raises(IntegrityError), transaction.atomic():
        BackupRestoreRequest.objects.create(timestamp=STAMP, preflight_id=uuid.uuid4())


def test_host_receipt_survives_database_rollback_and_blocks_replay(admin_client, catalog):
    response = restore(admin_client, preflight(admin_client))
    identifier = response.data['data']['id']
    payload = copy.deepcopy(catalog)
    payload['restore_receipts'] = [{'id': identifier, 'timestamp': STAMP, 'status': 'succeeded',
        'error': '', 'created_at': '2026-10-16T01:02:03+00:00', 'completed_at': '2026-10-16T01:03:03+00:00'}]
    runner_heartbeat(payload)
    assert claim_restore() is None
    assert BackupRestoreRequest.objects.get().status == 'succeeded'
    BackupRestoreRequest.objects.all().delete()  # 模拟恢复到登记请求之前的快照
    assert admin_client.get(BASE).data['data']['restore_requests'][0]['id'] == identifier


@pytest.mark.parametrize('change', ['path', 'checksum', 'bytes', 'length', 'time'])
def test_heartbeat_rejects_untrusted_catalog(catalog, change):
    payload = copy.deepcopy(catalog)
    if change == 'length':
        payload['directory_label'] = 'a' * 201
    elif change == 'time':
        payload['artifacts'][0]['created_at'] = 'not-a-date'
    else:
        field, value = {'path': ('name', '../../secrets'), 'checksum': ('sha256', 'bad'), 'bytes': ('bytes', -1)}[change]
        payload['artifacts'][0]['artifacts'][0][field] = value
    with pytest.raises(ValueError):
        runner_heartbeat(payload)
