"""Legacy approval and direct notification writes reauthorize before idempotency."""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.approvals import views as approvals
from apps.approvals.models import ApprovalRequest
from apps.auth_app.models import AuthSession
from apps.auth_app.sessions import issue_session, session_id
from apps.core.models import DataScopeGrant, IdempotencyRecord, OutboxEvent
from apps.logs.models import OperationLog
from apps.notifications import views as notifications
from apps.notifications.models import Notification
from apps.permissions.models import Role, UserRole

pytestmark = pytest.mark.django_db
User = get_user_model()
OPERATIONS = ('create', 'approve', 'reject', 'cancel', 'notify')


def jwt_client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(issue_session(user).access_token))
    return client


def prepare(client, actor, peer, operation):
    row = None
    if operation == 'notify':
        path = '/api/v1/notifications/'
        payload = {'recipient_ids': [str(peer.pk)], 'title': 'Private notification', 'content': 'Private body'}
    elif operation == 'create':
        path = '/api/v1/approvals/'
        payload = {'assignee_id': str(peer.pk), 'title': 'Private approval', 'content': 'Private body'}
    else:
        row = ApprovalRequest.objects.create(applicant=actor if operation == 'cancel' else peer,
            assignee=peer if operation == 'cancel' else actor, title='before', content='before')
        path = '/api/v1/approvals/' + str(row.pk) + '/' + operation + '/'
        payload = {} if operation == 'cancel' else {'comment': 'Private decision'}

    def send(key='fixture'):
        return client.post(path, payload, format='json', HTTP_IDEMPOTENCY_KEY=key)

    def unchanged():
        assert ApprovalRequest.objects.count() == (1 if row else 0)
        if row:
            row.refresh_from_db()
            assert row.status == 'pending' and row.decided_by_id is None and row.decision_comment == ''
        assert not Notification.objects.exists()
        assert not OutboxEvent.objects.exists()
        assert not IdempotencyRecord.objects.exists()
        assert not OperationLog.objects.filter(resource__in=('notification', 'approval')).exists()

    return send, unchanged, row


@pytest.mark.parametrize('operation', OPERATIONS)
@pytest.mark.parametrize('change,expected', [({'is_active': False}, 401), ({'must_change_password': True}, 403)])
def test_stale_entry_identity_cannot_mutate(admin_user, member_user, operation, change, expected):
    client = APIClient()
    client.force_authenticate(admin_user)
    send, unchanged, _ = prepare(client, admin_user, member_user, operation)
    User.objects.filter(pk=admin_user.pk).update(**change)
    assert send().status_code == expected
    unchanged()


@pytest.mark.parametrize('operation', OPERATIONS)
@pytest.mark.parametrize('change', ('device', 'version', 'password'))
def test_jwt_revoked_after_authentication_before_business_lock(admin_user, member_user, operation, change):
    send, unchanged, _ = prepare(jwt_client(admin_user), admin_user, member_user, operation)
    module = notifications if operation == 'notify' else approvals
    original = module.authorize_write

    def revoke(request, code=None, **kwargs):
        if change == 'device':
            AuthSession.objects.filter(pk=session_id(request.auth)).update(revoked_at=timezone.now())
        elif change == 'version':
            User.objects.filter(pk=request.user.pk).update(session_version=request.user.session_version + 1)
        else:
            updated = User.objects.get(pk=request.user.pk)
            updated.set_unusable_password()
            updated.save(update_fields=['password'])
        return original(request, code, **kwargs)

    with patch.object(module, 'authorize_write', side_effect=revoke) as check:
        assert send().status_code == 401
    check.assert_called_once()
    unchanged()


def test_direct_notification_rechecks_staff_after_initial_permission(admin_user, member_user):
    client = APIClient()
    client.force_authenticate(admin_user)
    send, unchanged, _ = prepare(client, admin_user, member_user, 'notify')
    User.objects.filter(pk=admin_user.pk).update(is_staff=False, is_superuser=False)
    assert send().status_code == 403
    unchanged()


@pytest.mark.parametrize('operation', ('create', 'approve', 'reject', 'cancel'))
def test_approval_participant_does_not_require_admin_or_new_permission(member_user, admin_user, operation):
    send, _, _ = prepare(jwt_client(member_user), member_user, admin_user, operation)
    assert send().status_code == (201 if operation == 'create' else 200)


@pytest.mark.parametrize('operation', OPERATIONS)
def test_audit_failure_rolls_back_business_event_and_receipt(admin_user, member_user, operation):
    send, unchanged, _ = prepare(jwt_client(admin_user), admin_user, member_user, operation)
    with patch('apps.logs.audit.write_audit', side_effect=RuntimeError('fixture audit failure')):
        assert send().status_code == 500
    unchanged()


@pytest.mark.parametrize('operation', ('create', 'approve', 'reject', 'notify'))
@pytest.mark.parametrize('change,expected', [({'is_active': False}, 401), ({'must_change_password': True}, 403)])
def test_successful_idempotency_receipt_still_requires_fresh_identity(admin_user, member_user,
                                                                    operation, change, expected):
    client = APIClient()
    client.force_authenticate(admin_user)
    send, _, _ = prepare(client, admin_user, member_user, operation)
    assert send().status_code == (201 if operation in ('create', 'notify') else 200)
    before = (ApprovalRequest.objects.count(), Notification.objects.count(), OutboxEvent.objects.count(),
              IdempotencyRecord.objects.count(), OperationLog.objects.filter(resource__in=('approval', 'notification')).count())
    User.objects.filter(pk=admin_user.pk).update(**change)
    response = send()
    assert response.status_code == expected
    assert 'Idempotency-Replayed' not in response
    assert before == (ApprovalRequest.objects.count(), Notification.objects.count(), OutboxEvent.objects.count(),
        IdempotencyRecord.objects.count(), OperationLog.objects.filter(resource__in=('approval', 'notification')).count())


@pytest.mark.parametrize('operation', ('create', 'approve', 'reject', 'notify'))
def test_successful_receipt_cannot_replay_after_device_revoked_mid_request(admin_user, member_user, operation):
    send, _, _ = prepare(jwt_client(admin_user), admin_user, member_user, operation)
    assert send().status_code == (201 if operation in ('create', 'notify') else 200)
    before = (Notification.objects.count(), OutboxEvent.objects.count(), OperationLog.objects.count())
    module = notifications if operation == 'notify' else approvals
    original = module.authorize_write

    def revoke(request, code=None, **kwargs):
        AuthSession.objects.filter(pk=session_id(request.auth)).update(revoked_at=timezone.now())
        return original(request, code, **kwargs)

    with patch.object(module, 'authorize_write', side_effect=revoke):
        response = send()
    assert response.status_code == 401 and 'Idempotency-Replayed' not in response
    assert before == (Notification.objects.count(), OutboxEvent.objects.count(), OperationLog.objects.count())


def test_creation_rechecks_scope_after_serializer_before_idempotency(member_user, admin_user):
    role = Role.objects.create(name='fixture')
    UserRole.objects.create(user=member_user, role=role)
    grant = DataScopeGrant.objects.create(role=role, resource='user', scope='all')
    send, unchanged, _ = prepare(jwt_client(member_user), member_user, admin_user, 'create')
    original = approvals.authorize_write

    def restrict(request, code=None, **kwargs):
        assert admin_user.pk in kwargs['related_users']
        DataScopeGrant.objects.filter(pk=grant.pk).update(scope='self')
        return original(request, code, **kwargs)

    with patch.object(approvals, 'authorize_write', side_effect=restrict):
        assert send().status_code == 400
    unchanged()


def test_assignee_changed_before_application_lock_is_rechecked(admin_user, member_user):
    send, _, row = prepare(jwt_client(admin_user), admin_user, member_user, 'approve')
    original = approvals.with_idempotency

    def reassign(request, scope, callback, **kwargs):
        ApprovalRequest.objects.filter(pk=row.pk).update(assignee=member_user)
        return original(request, scope, callback, **kwargs)

    with patch.object(approvals, 'with_idempotency', side_effect=reassign):
        assert send().status_code == 404
    row.refresh_from_db()
    assert row.status == 'pending'
    assert not OutboxEvent.objects.exists() and not OperationLog.objects.filter(resource='approval').exists()


def test_direct_notification_success_audits_hash_without_content_and_replay_does_not_duplicate(admin_user, member_user):
    send, _, _ = prepare(jwt_client(admin_user), admin_user, member_user, 'notify')
    assert send().status_code == 201
    assert send()['Idempotency-Replayed'] == 'true'
    assert Notification.objects.count() == 1
    log = OperationLog.objects.get(resource='notification')
    assert log.audit_version == 1 and log.after_values['content_length'] == len('Private body')
    assert log.description == 'sent_count=1'
    assert 'Private body' not in str(log.after_values) and 'Private notification' not in str(log.after_values)
