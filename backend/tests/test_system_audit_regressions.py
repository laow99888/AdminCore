import pytest
from rest_framework.test import APIClient

from apps.auth_app.models import User
from apps.core.models import Tenant, TenantMembership
from apps.core.tenancy import tenant_context
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.permissions.permissions import permission_codes
from apps.logs.models import OperationLog


@pytest.mark.django_db
def test_tenant_role_and_user_assignment_api(settings):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    tenant = Tenant.objects.create(slug='audit-rbac', name='Audit RBAC')
    admin = User.objects.create_superuser('audit-admin', password='Audit-only-Strong#4927')
    client = APIClient(raise_request_exception=False)
    client.force_authenticate(admin)
    headers = {'HTTP_X_ADMINCORE_TENANT': str(tenant.pk)}
    with tenant_context(tenant.pk):
        permission = Permission.objects.create(name='Audit read', code='audit:read', resource='audit', action='read')
    created_role = client.post('/api/v1/permissions/roles/', {'name': 'Audit role', 'permission_ids': [str(permission.pk)]}, format='json', **headers)
    assert created_role.status_code == 201, created_role.data
    role = Role.all_objects.get(name='Audit role')
    link = RolePermission.all_objects.get(role=role, permission=permission)
    created_user = client.post('/api/v1/users/', {'username': 'audit-assigned', 'password': 'Audit-only-Strong#9274', 'role_ids': [str(role.pk)], 'must_change_password': False}, format='json', **headers)
    assert created_user.status_code == 201, created_user.data
    user = User.objects.get(username='audit-assigned')
    user_link = UserRole.all_objects.get(user=user, role=role)
    TenantMembership.objects.create(user=user, tenant=tenant)
    with tenant_context(tenant.pk):
        codes = permission_codes(user)
        visible_links = UserRole.objects.filter(user=user).count()
        visible_permission_links = RolePermission.objects.filter(role=role).count()
    patched_role = client.patch(f'/api/v1/permissions/roles/{role.pk}/', {'permission_ids': [str(permission.pk)], 'version': role.version}, format='json', **headers)
    patched_user = client.patch(f'/api/v1/users/{user.pk}/', {'role_ids': [str(role.pk)], 'version': user.profile_version}, format='json', **headers)
    assert link.tenant_id == tenant.pk
    assert user_link.tenant_id == tenant.pk
    assert codes == ['audit:read']
    assert patched_role.status_code == 200
    assert patched_user.status_code == 200
    # 历史 NULL 关联不能导致重存 500，也不能删除另一个租户的分配。
    other = Tenant.objects.create(slug='other-rbac', name='Other RBAC')
    other_role = Role.all_objects.create(tenant=other, name='Other role')
    UserRole.all_objects.create(tenant=other, user=user, role=other_role)
    RolePermission.all_objects.filter(role=role).update(tenant=None)
    UserRole.all_objects.filter(user=user, role=role).update(tenant=None)
    role.refresh_from_db(); user.refresh_from_db()
    assert client.patch(f'/api/v1/permissions/roles/{role.pk}/', {'permission_ids': [str(permission.pk)], 'version': role.version}, format='json', **headers).status_code == 200
    assert client.patch(f'/api/v1/users/{user.pk}/', {'role_ids': [str(role.pk)], 'version': user.profile_version}, format='json', **headers).status_code == 200
    assert UserRole.all_objects.get(user=user, role=other_role).tenant_id == other.pk
    assert UserRole.all_objects.get(user=user, role=role).tenant_id == tenant.pk
    assert RolePermission.all_objects.get(role=role).tenant_id == tenant.pk


@pytest.mark.django_db
def test_field_permission_change_is_in_role_audit(settings):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = False
    admin = User.objects.create_superuser('audit-policy-admin', password='Audit-only-Strong#4927')
    client = APIClient()
    client.force_authenticate(admin)
    role = Role.objects.create(name='Audit field restriction', field_permissions={'user': {'read': ['id'], 'write': []}})
    response = client.patch(f'/api/v1/permissions/roles/{role.pk}/', {'version': 1, 'field_permissions': {'user': {'read': ['id', 'phone', 'email'], 'write': []}}}, format='json')
    assert response.status_code == 200, response.data
    audit = OperationLog.objects.get(resource='role', resource_id=str(role.pk))
    role.refresh_from_db()
    assert audit.before_values != audit.after_values
    assert audit.after_values['field_permissions'] == role.field_permissions


@pytest.mark.django_db(transaction=True)
def test_avatar_scan_audit_failure_keeps_previous_avatar(settings):
    from unittest.mock import patch
    from tests.clamd_fixture import clamd_fixture
    from tests.test_personal_profile import image_upload
    from apps.files.models import FileModel
    settings.ADMINCORE_MULTI_TENANT_ENABLED = False
    user = User.objects.create_user('audit-avatar', password='Audit-only-Strong#4927')
    client = APIClient()
    login = client.post('/api/v1/auth/login/', {'username': user.username, 'password': 'Audit-only-Strong#4927'}, format='json')
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + login.json()['access'])
    first = client.post('/api/v1/auth/avatar/', {'profile_version': 1, 'file': image_upload()}, format='multipart')
    assert first.status_code == 200
    user.refresh_from_db()
    old = user.avatar_file
    with clamd_fixture() as (config, scans), patch('apps.logs.audit.write_audit', side_effect=RuntimeError('audit-probe-failure')):
        settings.ADMINCORE_ANTIVIRUS = config
        response = client.post('/api/v1/auth/avatar/', {'profile_version': 2, 'file': image_upload()}, format='multipart')
    user.refresh_from_db()
    old.refresh_from_db()
    new = FileModel.objects.get(pk=user.avatar_file_id)
    assert response.status_code == 503
    assert not old.is_deleted
    assert user.avatar_file_id == old.pk
    assert not new.is_deleted
    assert new.file.storage.exists(new.file.name)
