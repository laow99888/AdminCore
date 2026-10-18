"""字段诊断解释真实的策略组合，绝不能成为业务读取或身份枚举入口。"""
from dataclasses import replace
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.core.models import DataScopeGrant, Tenant, TenantMembership
from apps.core.tenancy import clear_current_tenant, tenant_context
from apps.permissions.field_permissions import allowed_fields
from apps.permissions.models import Permission, Role, RolePermission, UserRole

pytestmark = pytest.mark.django_db
URL = '/api/v1/permissions/field-diagnostics/'


def diagnose(client, user, **overrides):
    return client.post(URL, {'user_id': str(user.pk), 'resource': 'user', 'field': 'email',
                             'operation': 'read', **overrides}, format='json')


def assign(user, name, policies=None, *, active=True, codes=()):
    role = Role.objects.create(name=name, is_active=active, field_permissions=policies or {})
    UserRole.objects.create(user=user, role=role)
    for code in codes:
        resource, action = code.split(':')
        permission, _ = Permission.objects.get_or_create(code=code, defaults={
            'name': code, 'resource': resource, 'action': action})
        RolePermission.objects.create(role=role, permission=permission)
    return role


def test_diagnostic_matches_field_union_and_permission_sources(admin_client, member_user):
    restricted = assign(member_user, 'restricted', {'user': {'read': ['email'], 'write': []}}, codes=['user:read'])
    assign(member_user, 'legacy', codes=['user:update'])
    assign(member_user, 'disabled', {'user': {'read': ['phone'], 'write': ['email']}}, active=False)
    response = diagnose(admin_client, member_user)
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'private, no-store'
    result = response.json()['data']
    assert result['field_reason'] == 'explicit_union'
    assert result['field_allowed'] and result['operation_allowed']
    assert result['permission_code'] == 'user:read'
    assert result['row_access'] == 'not_evaluated'
    assert result['roles'][0]['id']
    assert 'member@example.com' not in response.content.decode()
    assert 'username' not in result and 'email' not in result
    denied = diagnose(admin_client, member_user, operation='update').json()['data']
    assert denied['operation_allowed'] and not denied['field_allowed']
    assert denied['field_allowed'] == ('email' in allowed_fields(member_user, 'user', 'write'))
    restricted.field_permissions = {'user': {'read': [], 'write': ['email']}}
    restricted.save()
    assert diagnose(admin_client, member_user, operation='update').json()['data']['field_allowed']
    restricted.is_active = False
    restricted.save()
    updated = diagnose(admin_client, member_user).json()['data']
    assert updated['field_reason'] == 'legacy_unrestricted' and updated['field_allowed']
    assert not updated['operation_allowed']


def test_field_allowance_never_implies_function_or_business_access(admin_client, member_user):
    assign(member_user, 'unrestricted')
    data = diagnose(admin_client, member_user).json()['data']
    assert data['field_allowed'] and not data['operation_allowed']
    role = assign(member_user, 'self', codes=['user:read'])
    DataScopeGrant.objects.create(role=role, resource='user', scope='self')
    result = diagnose(admin_client, member_user).json()['data']
    assert result['data_scope'] == [{'role_id': str(role.pk), 'active': True, 'scope': 'self'}]
    assert result['row_access'] == 'not_evaluated'


def test_admin_and_password_deactivation_are_explained(admin_client, admin_user, member_user):
    result = diagnose(admin_client, admin_user).json()['data']
    assert result['field_reason'] == 'administrator' and result['operation_allowed']
    assign(member_user, 'can-read', codes=['user:read'])
    member_user.must_change_password = True
    member_user.save()
    result = diagnose(admin_client, member_user).json()['data']
    assert result['must_change_password'] and not result['operation_allowed']
    member_user.must_change_password = False
    member_user.is_active = False
    member_user.save()
    result = diagnose(admin_client, member_user).json()['data']
    assert not result['user_active'] and not result['operation_allowed']


@pytest.mark.parametrize('payload', [{'resource': 'unknown'}, {'field': 'password'}, {'operation': 'delete'},
                                     {'user_id': 'bad'}, {'field': 'profile.phone'}])
def test_rejects_unregistered_requests(admin_client, member_user, payload):
    assert diagnose(admin_client, member_user, **payload).status_code == 400


def test_non_admin_and_stale_admin_identity_cannot_diagnose(member_user, admin_user):
    client = APIClient()
    assign(member_user, 'ordinary-reader', codes=['role:read', 'user:read'])
    client.force_authenticate(member_user)
    assert diagnose(client, member_user).status_code == 403
    client.force_authenticate(admin_user)
    type(admin_user).objects.filter(pk=admin_user.pk).update(is_staff=False, is_superuser=False)
    assert diagnose(client, member_user).status_code == 403
    client.force_authenticate(None)
    assert diagnose(client, member_user).status_code in {401, 403}


def test_target_lookup_is_same_404_for_missing_and_outside_current_tenant(admin_client, member_user, settings):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    first = Tenant.objects.create(slug='first', name='First')
    second = Tenant.objects.create(slug='second', name='Second')
    TenantMembership.objects.create(tenant=second, user=member_user)
    try:
        hidden = diagnose(admin_client, member_user)
        client_response = admin_client.post(URL, {'user_id': str(member_user.pk), 'resource': 'user',
                                                'field': 'email', 'operation': 'read'}, format='json',
                                          HTTP_X_ADMINCORE_TENANT=str(first.pk))
        assert client_response.status_code == 404
        missing = admin_client.post(URL, {'user_id': str(uuid4()), 'resource': 'user', 'field': 'email',
                                         'operation': 'read'}, format='json', HTTP_X_ADMINCORE_TENANT=str(first.pk))
        assert missing.status_code == 404 and missing.json() == client_response.json()
        TenantMembership.objects.create(tenant=first, user=member_user)
        with tenant_context(first.pk):
            assign(member_user, 'First role', {'user': {'read': [], 'write': []}})
        with tenant_context(second.pk):
            assign(member_user, 'SECRET second role', {'user': {'read': ['email'], 'write': []}})
        response = admin_client.post(URL, {'user_id': str(member_user.pk), 'resource': 'user', 'field': 'email',
                                          'operation': 'read'}, format='json', HTTP_X_ADMINCORE_TENANT=str(first.pk))
        assert response.status_code == 200
        assert 'SECRET' not in response.content.decode() and not response.json()['data']['field_allowed']
        assert response.json()['data']['tenant_id'] == str(first.pk)
        assert hidden.status_code == 403  # No tenant context is rejected even for global admins.
    finally:
        clear_current_tenant()


def test_module_disable_and_unsupported_write_are_explicit(admin_client, member_user, settings):
    result = diagnose(admin_client, member_user, resource='files', field='original_name', operation='update').json()['data']
    assert result['permission_code'] is None and not result['operation_allowed']
    assign(member_user, 'posts', codes=['post:read', 'post:update'])
    settings.ADMINCORE_MODULES = ()
    result = diagnose(admin_client, member_user, resource='post', field='name').json()['data']
    assert not result['module_enabled'] and not result['operation_allowed']
    result = diagnose(admin_client, member_user, resource='role', field='name', operation='create').json()['data']
    assert result['permission_code'] == 'role:update' and result['requires_admin']
    settings.ADMINCORE_MODULES = ('organization',)
    result = diagnose(admin_client, member_user, resource='post', field='name').json()['data']
    assert result['requires_admin'] and not result['operation_allowed']


def test_explicit_business_contract_sources_and_aliases(admin_client, member_user, monkeypatch, settings):
    from apps.core import modules
    from apps.example.manifest import MODULE
    declaration = replace(MODULE, key='orders', field_policies=(('orders', ('code', 'lines.price')),),
                          permissions=(('orders', 'read', 'read', 'orders:read'),))
    monkeypatch.setattr(modules, 'MODULES', (*modules.MODULES, declaration))
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'orders')
    assign(member_user, 'Orders', {'orders': {'read': ['lines.price'], 'write': []}}, codes=['orders:read'])
    result = diagnose(admin_client, member_user, resource='orders', field='lines.price').json()['data']
    assert result['field_allowed'] and result['operation_allowed'] and result['permission_code'] == 'orders:read'
    result = diagnose(admin_client, member_user, resource='users').json()['data']
    assert result['resource'] == 'user'


def test_union_uses_every_effective_role_and_never_disabled_grants(admin_client, member_user):
    assign(member_user, 'restrict-first', {'user': {'read': [], 'write': ['email']}}, codes=['user:update'])
    assign(member_user, 'allow-second', {'user': {'read': ['email'], 'write': []}}, codes=['user:read'])
    assign(member_user, 'disabled-phone', {'user': {'read': ['phone'], 'write': ['phone']}}, active=False)
    for field in ('email', 'phone', 'username'):
        for operation in ('read', 'create', 'update'):
            result = diagnose(admin_client, member_user, field=field, operation=operation).json()['data']
            action = 'read' if operation == 'read' else 'write'
            assert result['field_allowed'] == (field in allowed_fields(member_user, 'user', action))


def test_revoked_device_cannot_run_metadata_diagnostics(admin_client, admin_user, member_user):
    from apps.auth_app.models import AuthSession
    from django.utils import timezone
    AuthSession.objects.filter(user=admin_user).update(revoked_at=timezone.now())
    assert diagnose(admin_client, member_user).status_code == 401
