"""管理编辑的显式版本、原子冲突及锁内用户授权回归。"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.permissions.models import Menu, Role, Permission, RolePermission
from apps.logs.models import OperationLog
from apps.users.views import UserViewSet

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture(params=['user', 'role', 'menu'])
def editable(request, member_user):
    if request.param == 'user':
        return member_user, f'/api/v1/users/{member_user.pk}/', 'first_name', 'profile_version'
    if request.param == 'role':
        row = Role.objects.create(name='version fixture')
        return row, f'/api/v1/permissions/roles/{row.pk}/', 'name', 'version'
    row = Menu.objects.create(name='version fixture', path='/version-fixture')
    return row, f'/api/v1/permissions/menus/{row.pk}/', 'name', 'version'


@pytest.mark.parametrize('method', ['patch', 'put'])
def test_missing_version_rejected_and_explicit_version_advances(admin_client, editable, method):
    row, url, field, version_field = editable
    body = {field: 'latest'}
    if isinstance(row, Menu):
        body['path'] = row.path
    assert getattr(admin_client, method)(url, body, format='json').status_code == 400
    result = getattr(admin_client, method)(url, {**body, 'version': 1}, format='json')
    assert result.status_code == 200, result.json()
    assert result.json()['data']['version'] == 2
    row.refresh_from_db()
    assert getattr(row, version_field) == 2 and getattr(row, field) == 'latest'
    before_logs = OperationLog.objects.count()
    stale = getattr(admin_client, method)(url, {**body, field: 'stale', 'version': 1}, format='json')
    assert stale.status_code == 409
    row.refresh_from_db()
    assert getattr(row, version_field) == 2 and getattr(row, field) == 'latest'
    assert OperationLog.objects.count() == before_logs


def test_stale_role_permissions_cannot_partially_write(admin_client):
    row = Role.objects.create(name='original')
    permission = Permission.objects.create(name='fixture', code='fixture:version', resource='fixture', action='read')
    url = f'/api/v1/permissions/roles/{row.pk}/'
    assert admin_client.patch(url, {'name': 'latest', 'version': 1}, format='json').status_code == 200
    response = admin_client.patch(url, {'name': 'stale', 'permission_ids': [str(permission.pk)], 'version': 1}, format='json')
    assert response.status_code == 409
    assert not RolePermission.objects.filter(role=row).exists()
    row.refresh_from_db()
    assert row.name == 'latest' and row.version == 2


def test_failed_audit_rolls_back_version_and_data(admin_client, editable):
    row, url, field, version_field = editable
    original = getattr(row, field)
    admin_client.raise_request_exception = False
    with patch('apps.logs.audit.write_audit', side_effect=RuntimeError('fixture unavailable')):
        result = admin_client.patch(url, {field: 'rollback', 'version': 1}, format='json')
    assert result.status_code == 500
    row.refresh_from_db()
    assert getattr(row, field) == original and getattr(row, version_field) == 1


def test_self_profile_and_bulk_invalidate_admin_draft(admin_client, member_client, member_user):
    url = f'/api/v1/users/{member_user.pk}/'
    assert member_client.patch('/api/v1/auth/profile/', {'profile_version': 1, 'bio': 'fresh'}, format='json').status_code == 200
    assert admin_client.patch(url, {'version': 1, 'first_name': 'stale'}, format='json').status_code == 409
    assert admin_client.post('/api/v1/users/bulk_action/', {'user_ids': [str(member_user.pk)], 'action': 'deactivate'}, format='json').status_code == 200
    assert admin_client.patch(url, {'version': 2, 'first_name': 'stale'}, format='json').status_code == 409
    member_user.refresh_from_db()
    assert member_user.profile_version == 3 and not member_user.is_active


@pytest.mark.parametrize('actions', [('deactivate', 'activate'), ('activate', 'activate')])
def test_bulk_audit_versions_match_persisted_steps_and_form_continuous_chain(admin_client, member_user, actions):
    from apps.logs.audit import snapshot
    # Start above the default version: audit must use the persisted version, not a fixed value.
    User.objects.filter(pk=member_user.pk).update(profile_version=7)
    member_user.refresh_from_db()
    original = snapshot('user', member_user)
    previous = original
    audit_steps = []
    for index, action in enumerate(actions, start=1):
        request_id = f'bulk-audit-version-{index}'
        result = admin_client.post('/api/v1/users/bulk_action/',
            {'user_ids': [str(member_user.pk)], 'action': action}, format='json',
            HTTP_X_REQUEST_ID=request_id)
        assert result.status_code == 200
        member_user.refresh_from_db()
        assert member_user.profile_version == 7 + index
        audit = OperationLog.objects.get(resource='user', resource_id=str(member_user.pk), request_id=request_id)
        actual = snapshot('user', member_user)
        assert audit.before_values == previous
        assert audit.after_values == actual
        assert audit.after_values['profile_version'] == member_user.profile_version
        assert audit.after_values['is_active'] == member_user.is_active == (action == 'activate')
        summary = OperationLog.objects.get(resource='user', resource_id='', request_id=request_id)
        assert summary.batch_results == [{'id': str(member_user.pk), 'status': 200}]
        audit_steps.append(audit)
        previous = actual
    assert audit_steps[0].before_values == original
    assert audit_steps[0].after_values == audit_steps[1].before_values


@pytest.mark.parametrize('operation', ['create', 'update', 'destroy', 'reset', 'bulk'])
def test_stale_admin_actor_cannot_write_after_staff_revocation(admin_user, member_user, operation):
    # force_authenticate intentionally holds the old actor; initial HasPermission passes.
    client = APIClient(); client.force_authenticate(admin_user)
    User.objects.filter(pk=admin_user.pk).update(is_staff=False, is_superuser=False)
    url = f'/api/v1/users/{member_user.pk}/'
    if operation == 'create':
        response = client.post('/api/v1/users/', {'username': 'no-create', 'email': 'no@example.test', 'password': 'FixtureStrong#83471'}, format='json')
    elif operation == 'update':
        response = client.patch(url, {'version': 1, 'first_name': 'no-write'}, format='json')
    elif operation == 'destroy':
        response = client.delete(url)
    elif operation == 'reset':
        response = client.post(url + 'reset_password/', {'password': 'FixtureStrong#83471'}, format='json')
    else:
        response = client.post('/api/v1/users/bulk_action/', {'user_ids': [str(member_user.pk)], 'action': 'deactivate'}, format='json')
    assert response.status_code == 403, response.json()
    member_user.refresh_from_db()
    assert member_user.first_name == '' and member_user.is_active and member_user.profile_version == 1
    assert not User.objects.filter(username='no-create').exists()
    assert not OperationLog.objects.filter(resource='user').exists()


def test_bulk_recomputes_scope_after_acquiring_user_locks(admin_client, member_user):
    original = UserViewSet._authorize_locked
    def fresh_scope(view, targets=(), extra_codes=()):
        rows = original(view, targets, extra_codes)
        return []  # A range restriction observed inside the locked authorization phase.
    with patch.object(UserViewSet, '_authorize_locked', fresh_scope):
        response = admin_client.post('/api/v1/users/bulk_action/', {'user_ids': [str(member_user.pk)], 'action': 'deactivate'}, format='json')
    assert response.status_code == 403
    assert response.json()['data']['results'] == [{'id': str(member_user.pk), 'status': 403}]
    member_user.refresh_from_db()
    assert member_user.is_active and member_user.profile_version == 1


@pytest.mark.parametrize('operation', ['create', 'update', 'destroy', 'reset', 'bulk'])
def test_real_jwt_rechecked_inside_transaction(admin_client, member_user, operation):
    from rest_framework.exceptions import AuthenticationFailed
    # Authentication was valid at the entry boundary; the lock-time session fails closed.
    with patch('apps.auth_app.sessions.locked_request_session', side_effect=AuthenticationFailed('revoked')) as locked:
        url = f'/api/v1/users/{member_user.pk}/'
        if operation == 'create':
            result = admin_client.post('/api/v1/users/', {'username': 'no-create', 'email': 'no@example.test', 'password': 'FixtureStrong#83471'}, format='json')
        elif operation == 'update': result = admin_client.patch(url, {'version': 1, 'first_name': 'no'}, format='json')
        elif operation == 'destroy': result = admin_client.delete(url)
        elif operation == 'reset': result = admin_client.post(url + 'reset_password/', {'password': 'FixtureStrong#83471'}, format='json')
        else: result = admin_client.post('/api/v1/users/bulk_action/', {'user_ids': [str(member_user.pk)], 'action': 'deactivate'}, format='json')
    assert result.status_code == 401
    locked.assert_called_once()
    member_user.refresh_from_db()
    assert member_user.is_active and member_user.profile_version == 1


def test_role_disabled_between_validation_and_user_write_rejected(admin_client, member_user):
    row = Role.objects.create(name='enabled-at-entry')
    original = UserViewSet._authorize_locked
    def disable(view, targets=(), extra_codes=()):
        Role.objects.filter(pk=row.pk).update(is_active=False)
        return original(view, targets, extra_codes)
    with patch.object(UserViewSet, '_authorize_locked', disable):
        response = admin_client.patch(f'/api/v1/users/{member_user.pk}/',
            {'version': 1, 'role_ids': [str(row.pk)]}, format='json')
    assert response.status_code == 400
    from apps.permissions.models import UserRole
    assert not UserRole.objects.filter(user=member_user, role=row).exists()
    member_user.refresh_from_db()
    assert member_user.profile_version == 1
