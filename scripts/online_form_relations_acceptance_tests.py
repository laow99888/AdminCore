"""真实 V2 生成模块登记、字段/行/租户权限与在线表单关联闭环。"""
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.cg_suppliers import manifest
from apps.cg_suppliers.models import Supplier
from apps.core.models import DataScopeGrant, Tenant
from apps.core.tenancy import tenant_context
from apps.online_forms.models import OnlineForm
from apps.online_forms.validators import validate_definition
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.online_forms.manifest import MODULE

pytestmark = pytest.mark.django_db
BASE = '/api/v1/online-forms/relation-acceptance/'


def grant_record_permissions(user):
    role = Role.objects.create(name='relation-record-' + str(uuid4()))
    UserRole.objects.create(user=user, role=role)
    for resource, action, name, code in MODULE.permissions:
        if action not in {'record_read', 'record_create', 'record_update'}:
            continue
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'name': name, 'resource': resource, 'action': action})
        RolePermission.objects.create(role=role, permission=permission)


def prepare(user, fields=('name',)):
    grant_record_permissions(user)
    role = Role.objects.create(name=str(uuid4()), field_permissions={'cg_suppliers': {'read': list(fields), 'write': []}})
    UserRole.objects.create(user=user, role=role)
    permission, _ = Permission.objects.get_or_create(code='cg_suppliers:read', defaults={'name': '读取供应商', 'resource': 'cg_suppliers', 'action': 'read'})
    RolePermission.objects.create(role=role, permission=permission)
    client = APIClient(); client.force_authenticate(user)
    return client, role


def form(user):
    return OnlineForm.objects.create(code='relation-acceptance', name='真实登记关联', status='published', created_by=user,
        definition=validate_definition({'schema_version': 2, 'fields': [{'key': 'supplier', 'label': '供应商', 'type': 'relation', 'resource': 'cg_suppliers'}]}))


def test_real_registration_title_field_and_row_scope_reauthorize_every_use(admin_user, member_user):
    client, role = prepare(member_user); source = form(admin_user)
    own = Supplier.objects.create(code='REL-SELF', name='当前可读供应商', creator=member_user)
    other = Supplier.objects.create(code='REL-OTHER', name='其他人的供应商', creator=admin_user)
    params = {'form_id': source.pk, 'field': 'supplier', 'selected': other.pk}
    response = client.get(BASE + 'relations/', params)
    assert response.status_code == 200, response.content
    assert response.json()['data'] == {'selected': None, 'items': [{'id': str(own.pk), 'title': own.name}], 'has_more': False}
    grant = DataScopeGrant.objects.create(role=role, resource='cg_suppliers', scope='all')
    assert len(client.get(BASE + 'relations/', params).json()['data']['items']) == 2
    saved = client.post(BASE + 'records/', {'data': {'supplier': str(other.pk)}}, format='json')
    assert saved.status_code == 201, saved.content
    record = saved.json()['data']; params = {'record_id': record['id'], 'field': 'supplier', 'selected': other.pk, 'resolve': 'true'}
    grant.scope = 'self'; grant.save()
    assert client.get(BASE + 'relations/', params).json()['data']['selected'] is None
    assert client.patch(BASE + 'records/' + record['id'] + '/', {'version': 1, 'data': record['data']}, format='json').status_code == 400
    role.field_permissions = {'cg_suppliers': {'read': ['code'], 'write': []}}; role.save()
    denied = client.get(BASE + 'relations/', params)
    assert denied.status_code == 400 and other.name not in denied.content.decode()


def test_real_source_disabled_permission_revoked_or_unregistered_fails_closed(admin_user, member_user, settings, monkeypatch):
    client, role = prepare(member_user); source = form(admin_user)
    row = Supplier.objects.create(code='REL', name='不得泄露', creator=member_user)
    payload = {'data': {'supplier': str(row.pk)}}
    assert client.post(BASE + 'records/', payload, format='json').status_code == 201
    role.is_active = False; role.save()
    assert client.post(BASE + 'records/', payload, format='json').status_code == 400
    role.is_active = True; role.save()
    monkeypatch.delattr(manifest, 'BUSINESS_SEARCH')
    assert client.get(BASE + 'relations/', {'form_id': source.pk, 'field': 'supplier'}).status_code == 400
    monkeypatch.setattr(manifest, 'BUSINESS_SEARCH', {'fields': ['name'], 'title_field': 'name'}, raising=False)
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'cg_suppliers')
    assert client.post(BASE + 'records/', payload, format='json').status_code == 400


def test_real_tenant_and_form_context_with_unscoped_platform_admin(settings, admin_user, admin_client):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    a, b = Tenant.objects.create(slug='relation-real-a', name='甲'), Tenant.objects.create(slug='relation-real-b', name='乙')
    with tenant_context(a.pk):
        source = form(admin_user); own = Supplier.objects.create(code='A', name='甲租户供应商', creator=admin_user)
    with tenant_context(b.pk):
        other = Supplier.objects.create(code='B', name='乙租户秘密', creator=admin_user)
    params = {'form_id': source.pk, 'field': 'supplier', 'selected': other.pk}
    response = admin_client.get(BASE + 'relations/', params)
    assert response.status_code == 200, response.content
    assert response.json()['data'] == {'selected': None, 'items': [{'id': str(own.pk), 'title': own.name}], 'has_more': False}
    assert admin_client.post(BASE + 'records/', {'form_id': source.pk, 'data': {'supplier': str(other.pk)}}, format='json').status_code == 400
    assert admin_client.get(BASE + 'relations/', params, HTTP_X_ADMINCORE_TENANT=str(b.pk)).status_code == 404


def test_undeclared_orm_paths_never_become_relation_resource(admin_client, admin_user):
    row = form(admin_user)
    row.definition['fields'][0]['resource'] = 'auth_app'; row.save()
    response = admin_client.get(BASE + 'relations/', {'form_id': row.pk, 'field': 'supplier'})
    assert response.status_code == 400
    choices = admin_client.get('/api/v1/online-forms/relation-resources/')
    assert choices.status_code == 200 and {'code': 'cg_suppliers', 'title': '供应商'} in choices.json()['data']
