"""角色字段策略必须贯穿读取、编辑和导出边界。"""

import pytest
from rest_framework.test import APIClient

from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.permissions.field_permissions import allowed_fields

pytestmark = pytest.mark.django_db


def grant(role, *codes):
    permissions = []
    for code in codes:
        permission = Permission.objects.create(name=code, code=code, resource=code.split(':')[0], action=code.split(':')[1])
        permissions.append(permission)
    RolePermission.objects.bulk_create([RolePermission(role=role, permission=item) for item in permissions])


def test_role_field_policy_rejects_unknown_fields(admin_client):
    response = admin_client.post('/api/v1/permissions/roles/', {
        'name': '受限字段角色',
        'field_permissions': {'user': {'read': ['username', 'not_a_user_field'], 'write': []}},
    }, format='json')
    assert response.status_code == 400
    assert 'field_permissions' in response.json()['data']


def test_field_policy_filters_read_rejects_write_and_export(admin_user, db):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    actor = User.objects.create_user('field-actor', 'field-actor@example.com', 'Field#12345')
    target = User.objects.create_user('field-target', 'field-target@example.com', 'Field#12345', first_name='原名')
    role = Role.objects.create(name='字段受限', field_permissions={
        'user': {'read': ['id', 'username', 'version'], 'write': ['first_name']},
    })
    grant(role, 'user:read', 'user:update', 'data_io:export')
    UserRole.objects.create(user=actor, role=role)

    client = APIClient()
    client.force_authenticate(actor)
    listed = client.get('/api/v1/users/')
    assert listed.status_code == 200
    row = listed.json()['data']['items'][0]
    assert set(row) <= {'id', 'username', 'version'}
    assert 'email' not in row
    detail = client.get(f'/api/v1/users/{target.pk}/')
    assert detail.status_code == 200
    assert set(detail.json()['data']) <= {'id', 'username', 'version'}

    denied = client.patch(f'/api/v1/users/{target.pk}/', {'email': 'blocked@example.com', 'version': target.profile_version}, format='json')
    assert denied.status_code == 403
    allowed = client.patch(f'/api/v1/users/{target.pk}/', {'first_name': '新名', 'version': target.profile_version}, format='json')
    assert allowed.status_code == 200

    exported = client.get('/api/v1/data-io/export/', {'resource': 'users', 'export_format': 'csv'})
    assert exported.status_code == 200
    assert exported.content.decode('utf-8-sig').splitlines()[0] == 'username'

    assert allowed_fields(actor, 'users', 'read') == {'id', 'username', 'version'}
