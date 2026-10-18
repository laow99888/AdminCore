"""真实生成模块上的全局搜索权限、范围和预算边界验收。"""
from dataclasses import replace
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.cg_suppliers import manifest
from apps.cg_suppliers.models import Supplier
from apps.core.business_search import search
from apps.core.models import DataScopeGrant, Tenant
from apps.core.tenancy import tenant_context
from apps.permissions.models import Permission, Role, RolePermission, UserRole

pytestmark = pytest.mark.django_db
ROOT = '/api/v1/business-search/'


def restricted(user, fields):
    role = Role.objects.create(name=str(uuid4()), field_permissions={'cg_suppliers': {'read': fields, 'write': []}})
    UserRole.objects.create(user=user, role=role)
    permission, _ = Permission.objects.get_or_create(code='cg_suppliers:read', defaults={'name': '读取供应商', 'resource': 'cg_suppliers', 'action': 'read'})
    RolePermission.objects.create(role=role, permission=permission)
    client = APIClient(); client.force_authenticate(user)
    return client, role


def groups(client, q, **kwargs):
    response = client.get(ROOT, {'q': q, **kwargs})
    assert response.status_code == 200, response.content
    assert response['Cache-Control'] == 'no-store'
    return response.json()['data']['groups']


def test_registered_sources_exact_and_contains_search_without_details(admin_client, admin_user):
    row = Supplier.objects.create(code='SEARCH-CODE', name='中文搜索供应商', creator=admin_user)
    result = groups(admin_client, '搜索')
    assert len(result) == 1 and result[0]['path'] == '/cg-suppliers'
    assert result[0]['items'][0]['id'] == str(row.pk)
    assert result[0]['items'][0]['title'] == row.name
    assert len(result[0]['items'][0]['values']) == 2
    assert 'creator' not in str(result) and 'version' not in str(result)
    assert groups(admin_client, 'SEARCH') == []  # eq字段不被悄悄扩大为模糊匹配。
    assert groups(admin_client, 'SEARCH-CODE')[0]['items'][0]['id'] == str(row.pk)


def test_search_matches_only_current_readable_fields_and_fallback_title(member_user, admin_user):
    row = Supplier.objects.create(code='PUBLIC-CODE', name='私密标题', creator=member_user)
    Supplier.objects.create(code='OTHER-OWNER', name='公开名称', creator=admin_user)
    client, role = restricted(member_user, ['code'])
    assert groups(client, '私密') == []
    result = groups(client, 'PUBLIC-CODE')
    assert result[0]['items'][0]['title'] == '供应商'
    assert '私密' not in str(result)
    assert groups(client, 'OTHER-OWNER') == []
    role.field_permissions = {'cg_suppliers': {'read': ['name'], 'write': []}}; role.save()
    assert groups(client, 'PUBLIC-CODE') == []
    assert groups(client, '私密')[0]['items'][0]['id'] == str(row.pk)
    role.field_permissions = {'cg_suppliers': {'read': [], 'write': []}}; role.save()
    assert groups(client, '私密') == []
    assert client.get(ROOT, {'q': '私密', 'source': 'cg_suppliers'}).status_code == 404


def test_revoked_permission_disabled_role_module_and_undeclared_sources_are_unavailable(member_user, settings, monkeypatch):
    client, role = restricted(member_user, ['name'])
    Supplier.objects.create(code='AA', name='Searchable', creator=member_user)
    assert groups(client, 'Search')
    role.is_active = False; role.save()
    assert groups(client, 'Search') == []
    role.is_active = True; role.save()
    RolePermission.objects.filter(role=role).delete()
    assert groups(client, 'Search') == []
    permission = Permission.objects.get(code='cg_suppliers:read')
    RolePermission.objects.create(role=role, permission=permission)
    assert groups(client, 'Search')
    monkeypatch.delattr(manifest, 'BUSINESS_SEARCH')
    assert groups(client, 'Search') == []
    monkeypatch.setattr(manifest, 'BUSINESS_SEARCH', {'fields': ['name'], 'title_field': 'name'}, raising=False)
    assert groups(client, 'Search')
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'cg_suppliers')
    assert groups(client, 'Search') == []


def test_data_scope_grants_do_not_expand_unconfigured_fallback(member_user, admin_user):
    client, role = restricted(member_user, ['name'])
    Supplier.objects.create(code='SELF', name='Match-Self', creator=member_user)
    Supplier.objects.create(code='OTHER', name='Match-Other', creator=admin_user)
    assert len(groups(client, 'Match')[0]['items']) == 1
    grant = DataScopeGrant.objects.create(role=role, resource='cg_suppliers', scope='all')
    assert len(groups(client, 'Match')[0]['items']) == 2
    grant.scope = 'self'; grant.save()
    assert len(groups(client, 'Match')[0]['items']) == 1


def test_tenant_boundary_including_unscoped_platform_admin(admin_user, settings):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    first = Tenant.objects.create(name='甲', slug='search-a')
    second = Tenant.objects.create(name='乙', slug='search-b')
    with tenant_context(first.pk):
        a = Supplier.objects.create(code='AA', name='Tenant-Match', creator=admin_user)
    with tenant_context(second.pk):
        Supplier.objects.create(code='BB', name='Tenant-Match', creator=admin_user)
        assert search(admin_user, 'Tenant')['groups'][0]['items'][0]['id'] != str(a.pk)
    with tenant_context(first.pk):
        result = search(admin_user, 'Tenant')['groups'][0]
        assert [row['id'] for row in result['items']] == [str(a.pk)]
    with tenant_context(None):
        assert search(admin_user, 'Tenant')['groups'] == []


@pytest.mark.parametrize('params', [{}, {'q': 'a'}, {'q': ' '}, {'q': 'a' * 81}, {'q': 'ab\x00'},
    {'q': ['ab', 'cd']}, {'q': 'valid', 'model': 'users.User'}, {'q': 'valid', 'source': ''},
    {'q': 'valid', 'source': 'a' * 81}, {'q': 'valid', 'source': ['cg_suppliers', 'cg_orders']}])
def test_strict_input_budget(admin_client, params):
    assert admin_client.get(ROOT, params).status_code == 400


@pytest.mark.parametrize('declaration', [None, {}, {'fields': ['name__regex'], 'title_field': 'name__regex'},
    {'fields': ['name', 'name'], 'title_field': 'name'}, {'fields': ['active'], 'title_field': 'active'},
    {'fields': ['name'], 'title_field': 'code'}, {'fields': 'name', 'title_field': 'name'}])
def test_invalid_source_declaration_fails_closed(admin_client, admin_user, monkeypatch, declaration):
    Supplier.objects.create(code='AA', name='Match-Secret', creator=admin_user)
    monkeypatch.setattr(manifest, 'BUSINESS_SEARCH', declaration)
    assert groups(admin_client, 'Match') == []


def test_result_limit_stable_order_no_count_and_literal_wildcards(admin_client, admin_user):
    for index in range(7):
        Supplier.objects.create(code=str(index), name='Match_%' + str(index), creator=admin_user)
    with CaptureQueriesContext(connection) as queries:
        result = groups(admin_client, 'Match_%')
    assert len(result[0]['items']) == 5 and result[0]['has_more'] is True
    assert result[0]['items'][0]['title'] == 'Match_%6'
    assert not any('COUNT(' in row['sql'].upper() for row in queries)
    assert groups(admin_client, 'Match_X') == []
    assert groups(admin_client, 'Match_')[0]['items'] == result[0]['items']


def test_unknown_source_has_same_response_as_unauthorized(member_user):
    client = APIClient(); client.force_authenticate(member_user)
    first = client.get(ROOT, {'q': 'Match', 'source': 'cg_suppliers'})
    second = client.get(ROOT, {'q': 'Match', 'source': 'unknown'})
    assert first.status_code == second.status_code == 404 and first.json() == second.json()
    assert APIClient().get(ROOT, {'q': 'Match'}).status_code == 401


def test_source_cap_and_explicit_source_selection(admin_user, monkeypatch):
    import apps.core.business_search as target
    entry = next(item for item in target.sources(admin_user) if item[0].key == 'cg_suppliers')
    entries = [(replace(entry[0], key='source_' + str(index)), *entry[1:]) for index in range(10)]
    monkeypatch.setattr(target, 'sources', lambda actor: iter(entries))
    Supplier.objects.create(code='AA', name='Match', creator=admin_user)
    result = search(admin_user, 'Match')
    assert len(result['groups']) == 8 and result['sources_limited'] is True
    assert search(admin_user, 'Match', 'source_9')['groups'][0]['source'] == 'source_9'
