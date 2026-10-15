from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.logs.models import OperationLog
from apps.tasks.models import TaskRecord

pytestmark = pytest.mark.django_db
URL = '/api/v1/tasks/cleanup/'


def old_task(user, **kwargs):
    row = TaskRecord.objects.create(name='fixture', creator=user, status='success', **kwargs)
    TaskRecord.objects.filter(pk=row.pk).update(created_at=timezone.now()-timedelta(days=60))
    return row


def preview(client, **kwargs):
    response = client.post(URL, {'days': 30, **kwargs}, format='json')
    assert response.status_code == 200
    return response.json()['data']


def execute(client, plan, **kwargs):
    return client.post(URL, {'days': 30, 'dry_run': False, 'confirmation': '执行清理',
        'preview_token': plan['preview_token'], **kwargs}, format='json')


def test_default_preview_has_no_deletion_and_execute_is_bounded(admin_client, admin_user):
    rows = [old_task(admin_user) for _ in range(3)]
    backup = old_task(admin_user, task_type='backup')
    plan = preview(admin_client, batch_size=2)
    assert plan['eligible'] == 3 and plan['selected'] == 2 and plan['more']
    assert plan['protected_backup_records'] == 1 and TaskRecord.objects.count() == 4
    # A newer eligible record is not silently included in an already reviewed plan.
    extra = old_task(admin_user)
    result = execute(admin_client, plan, batch_size=2)
    assert result.status_code == 200 and result.json()['data']['deleted'] == 2
    assert TaskRecord.objects.filter(pk=backup.pk).exists() and TaskRecord.objects.filter(pk=extra.pk).exists()
    assert TaskRecord.objects.filter(pk__in=[row.pk for row in rows]).count() == 1
    assert OperationLog.objects.filter(resource='task', action='delete').count() == 2
    assert execute(admin_client, plan, batch_size=2).status_code == 409


def test_preview_cannot_be_used_after_target_or_policy_changes(admin_client, admin_user):
    row = old_task(admin_user)
    plan = preview(admin_client)
    assert execute(admin_client, plan, days=31).status_code == 409
    TaskRecord.objects.filter(pk=row.pk).update(status='running')
    assert execute(admin_client, plan).status_code == 409
    assert TaskRecord.objects.filter(pk=row.pk).exists()


@pytest.mark.parametrize('values', [{'dry_run': False}, {'dry_run': False, 'confirmation': '执行清理'},
    {'dry_run': False, 'confirmation': '执行清理', 'preview_token': 'tampered'}])
def test_delete_requires_valid_confirmed_preview(admin_client, admin_user, values):
    row = old_task(admin_user)
    assert admin_client.post(URL, values, format='json').status_code in (400, 409)
    assert TaskRecord.objects.filter(pk=row.pk).exists()


def test_audit_failure_rolls_back_whole_batch(admin_client, admin_user):
    row = old_task(admin_user)
    plan = preview(admin_client)
    admin_client.raise_request_exception = False
    with patch('apps.tasks.history_cleanup.write_audit', side_effect=RuntimeError('fixture')):
        assert execute(admin_client, plan).status_code == 500
    assert TaskRecord.objects.filter(pk=row.pk).exists()
    assert not OperationLog.objects.filter(resource='task', action='delete').exists()


def test_preview_and_execute_recheck_device(admin_client, admin_user):
    from rest_framework.exceptions import AuthenticationFailed
    row = old_task(admin_user)
    plan = preview(admin_client)
    with patch('apps.auth_app.sessions.locked_request_session', side_effect=AuthenticationFailed('revoked')):
        assert admin_client.post(URL, {}, format='json').status_code == 401
        assert execute(admin_client, plan).status_code == 401
    assert TaskRecord.objects.filter(pk=row.pk).exists()


def test_preview_signature_expires_after_fifteen_minutes(admin_client, admin_user):
    row = old_task(admin_user)
    with patch('django.core.signing.time.time', return_value=1000):
        plan = preview(admin_client)
    with patch('django.core.signing.time.time', return_value=1901):
        assert execute(admin_client, plan).status_code == 409
    assert TaskRecord.objects.filter(pk=row.pk).exists()
