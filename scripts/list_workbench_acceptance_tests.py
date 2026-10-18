"""在实际生成模块和独占数据库中验证列表工作台，不访问业务运行库。"""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, local
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import close_old_connections, connection
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.cg_suppliers.models import Supplier
from apps.cg_suppliers import extensions
from apps.cg_orders.models import PurchaseOrder
from apps.core.models import SavedListView, Tenant
from apps.core.tenancy import tenant_context
from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole

pytestmark = pytest.mark.django_db
ROOT = '/api/v1/cg-suppliers/records/'


def definition(*conditions, match='all', filters=None, ordering=''):
    return {'filters': filters or {}, 'advanced': {'match': match, 'conditions': list(conditions)}, 'ordering': ordering}


def condition(field='name', op='contains', value='甲'):
    return {'field': field, 'op': op, 'value': value}


def save(client, value=None, **changes):
    return client.post(ROOT + 'query-views/', {'name': '我的查询', 'shared': False, 'definition': value or definition(), **changes}, format='json')


def selection(*rows):
    return [{'id': str(row.pk), 'version': row.version} for row in rows]


def preview(client, *rows):
    response = client.post(ROOT + 'bulk-preview/', {'selection': selection(*rows)}, format='json')
    assert response.status_code == 200, response.content
    return response.json()['data']


def execute(client, token, key='bulk-test'):
    return client.post(ROOT + 'bulk-delete/', {'preview_token': token, 'confirmation': '删除选中记录'}, format='json', HTTP_IDEMPOTENCY_KEY=key)


def restricted(user, *, read=None, codes=('read', 'delete')):
    role = Role.objects.create(name=str(uuid4()), field_permissions={'cg_suppliers': {'read': read or ['code', 'name', 'active'], 'write': []}})
    UserRole.objects.create(user=user, role=role)
    for action in codes:
        code = 'cg_suppliers:' + action
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'name': code, 'resource': 'cg_suppliers', 'action': action})
        RolePermission.objects.create(role=role, permission=permission)
    client = APIClient(); client.force_authenticate(user)
    return client, role


@pytest.mark.parametrize('match,conditions,expected', [
    ('all', [condition(), condition('active', 'eq', True)], ['A']),
    ('any', [condition(), condition('active', 'eq', True)], ['A', 'B', 'C']),
    ('all', [condition('name', 'ne', '甲乙')], ['B', 'C']),
    ('all', [], ['A', 'B', 'C']),
])
def test_advanced_boolean_combinations(admin_client, admin_user, match, conditions, expected):
    for code, name, active in [('A', '甲乙', True), ('B', '甲丙', False), ('C', '丁', True)]:
        Supplier.objects.create(code=code, name=name, active=active, creator=admin_user)
    response = admin_client.get(ROOT, {'advanced': json.dumps({'match': match, 'conditions': conditions}), 'ordering': 'code'})
    assert response.status_code == 200, response.content
    assert [item['code'] for item in response.json()['data']['items']] == expected


@pytest.mark.parametrize('advanced', [
    '{', '[]', 'null', '{}', '{"match":"all","conditions":[],"extra":1}',
    json.dumps({'match': 'all', 'conditions': [condition()] * 11}),
    json.dumps({'match': 'all', 'conditions': [condition('creator__password')]}),
    json.dumps({'match': 'all', 'conditions': [condition('name', 'regex', '.*')]}),
    json.dumps({'match': 'any', 'conditions': [condition('active', 'contains', 'true')]}),
    json.dumps({'match': 'any', 'conditions': [condition('active', 'eq', 'not-bool')]}),
    json.dumps({'match': 'any', 'conditions': [condition(value=['nested'])]}),
    json.dumps({'match': [], 'conditions': []}),
    json.dumps({'match': 'all', 'conditions': [condition(value='a' * 201)]}),
    ' ' * 4097,
])
def test_advanced_rejects_unregistered_structure_operators_and_types(admin_client, advanced):
    assert admin_client.get(ROOT, {'advanced': advanced}).status_code == 400


def test_condition_permissions_cannot_be_bypassed_by_or_sort_spacing_or_saved_views(member_user, admin_client, admin_user):
    member, _ = restricted(member_user, read=['code'])
    hidden = definition(condition(value='private-value'))
    assert member.get(ROOT, {'advanced': json.dumps(hidden['advanced'])}).status_code == 403
    assert member.get(ROOT, {'ordering': ' name '}).status_code == 400  # 未登记排序字段。
    shared = save(admin_client, hidden, shared=True)
    assert shared.status_code == 200, shared.content
    response = member.get(ROOT + 'query-views/')
    assert response.status_code == 200 and response.json()['data'] == {'items': [], 'unavailable': 1}
    assert 'private-value' not in str(response.json())
    assert save(member, hidden).status_code == 403


def test_whitespace_sort_cannot_infer_hidden_registered_field(member_user):
    member, _ = restricted(member_user, read=['name'])
    for ordering in ['code', ' code ', ' -code ']:
        assert member.get(ROOT, {'ordering': ordering}).status_code == 403


def test_advanced_filter_is_shared_by_export(admin_client, admin_user):
    Supplier.objects.create(code='A', name='甲供应商', creator=admin_user)
    Supplier.objects.create(code='B', name='乙供应商', creator=admin_user)
    response = admin_client.get('/api/v1/data-io/business/export/', {'resource': 'cg_suppliers',
        'advanced': json.dumps(definition(condition())['advanced'])})
    assert response.status_code == 200, response.content
    content = response.content.decode('utf-8-sig')
    assert '甲供应商' in content and '乙供应商' not in content


def test_personal_shared_views_versions_redaction_and_audit(admin_client, admin_user, member_user):
    member, role = restricted(member_user)
    private = save(admin_client, definition(condition(value='private-secret')))
    assert private.status_code == 200, private.content
    shared = save(admin_client, definition(condition()), name='共享视图', shared=True).json()['data']
    assert save(member, shared=True).status_code == 403
    assert [row['id'] for row in member.get(ROOT + 'query-views/').json()['data']['items']] == [shared['id']]
    own = save(member, definition(condition(value='personal-value'))).json()['data']
    update = save(member, definition(), id=own['id'], version=own['version'])
    assert update.status_code == 200 and update.json()['data']['version'] == 2
    assert save(member, definition(), id=own['id'], version=1).status_code == 409
    assert member.delete(ROOT + 'query-views/', {'id': shared['id'], 'version': 1}, format='json').status_code == 404
    role.field_permissions = {'cg_suppliers': {'read': ['code'], 'write': []}}; role.save()
    response = member.get(ROOT + 'query-views/').json()['data']
    assert response['unavailable'] == 1  # 个人方案已更新为空，只有共享方案失效。
    assert 'private-secret' not in str(response) and 'personal-value' not in str(response)
    logs = OperationLog.objects.filter(resource='list_view')
    assert logs.count() == 4 and 'private-secret' not in str(list(logs.values('before_values', 'after_values')))
    assert admin_client.get(ROOT + 'query-views/?unknown=1').status_code == 400


def test_stale_owner_can_delete_unavailable_view_without_reading_old_values(member_user):
    member, role = restricted(member_user)
    own = save(member, definition(condition(value='old-sensitive-filter'))).json()['data']
    role.field_permissions = {'cg_suppliers': {'read': ['code'], 'write': []}}; role.save()
    result = member.get(ROOT + 'query-views/').json()['data']
    assert result['unavailable'] == 1 and len(result['items']) == 1
    assert result['items'][0]['available'] is False and 'old-sensitive-filter' not in str(result)
    assert member.delete(ROOT + 'query-views/', {'id': own['id'], 'version': own['version']}, format='json').status_code == 200


def test_demoted_shared_view_owner_cannot_edit_or_delete_shared_view(admin_client, admin_user):
    shared = save(admin_client, shared=True).json()['data']
    admin_user.is_staff = admin_user.is_superuser = False; admin_user.save()
    member, _ = restricted(admin_user)
    row = member.get(ROOT + 'query-views/').json()['data']['items'][0]
    assert row['editable'] is False
    assert member.delete(ROOT + 'query-views/', {'id': shared['id'], 'version': 1}, format='json').status_code == 404


@pytest.mark.parametrize('value', [definition(filters={'page': '1'}), definition(filters={'search': 'all'}),
    definition(filters={'active': 'invalid'}), definition(ordering='creator__password'), definition(filters={'code': 'x' * 201})])
def test_saved_view_reuses_list_validation(admin_client, value):
    assert save(admin_client, value).status_code == 400
    assert SavedListView.objects.count() == 0


def test_view_limit_and_duplicate_name_are_serialized(admin_client, admin_user):
    assert save(admin_client).status_code == 200
    assert save(admin_client).status_code == 409
    for index in range(1, 30):
        SavedListView.objects.create(owner=admin_user, module='cg_suppliers', name=str(index), definition=definition(), schema_digest='x')
    assert save(admin_client, name='31').status_code == 400
    assert save(admin_client, shared=True).status_code == 200


def test_saved_view_and_token_tenant_isolation(admin_client, admin_user, settings):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    one = Tenant.objects.create(slug='one', name='One'); two = Tenant.objects.create(slug='two', name='Two')
    admin_client.credentials(HTTP_AUTHORIZATION=admin_client._credentials['HTTP_AUTHORIZATION'], HTTP_X_ADMINCORE_TENANT=str(one.pk))
    first = save(admin_client, shared=True).json()['data']
    with tenant_context(one.pk):
        row = Supplier.objects.create(code='T', name='One', creator=admin_user)
    token = preview(admin_client, row)['preview_token']
    admin_client.credentials(HTTP_AUTHORIZATION=admin_client._credentials['HTTP_AUTHORIZATION'], HTTP_X_ADMINCORE_TENANT=str(two.pk))
    assert admin_client.get(ROOT + 'query-views/').json()['data']['items'] == []
    assert admin_client.delete(ROOT + 'query-views/', {'id': first['id'], 'version': 1}, format='json').status_code == 404
    assert preview(admin_client, row)['items'][0]['status'] == 'unavailable'
    assert execute(admin_client, token).status_code == 400


def test_bulk_preview_partial_execution_versions_extensions_and_idempotency(admin_client, admin_user, monkeypatch):
    rows = [Supplier.objects.create(code=str(index), name='Item', creator=admin_user) for index in range(4)]
    planned = preview(admin_client, *rows)
    assert planned['ready'] == 4 and Supplier.objects.count() == 4
    Supplier.objects.filter(pk=rows[1].pk).update(version=2)
    def before_delete(*, actor, instance):
        if instance.pk == rows[2].pk:
            raise ValidationError('自定义业务约束')
    monkeypatch.setattr(extensions, 'before_delete', before_delete)
    result = execute(admin_client, planned['preview_token'])
    assert result.status_code == 200, result.content
    assert [item['status'] for item in result.json()['data']['items']] == ['deleted', 'conflict', 'blocked', 'deleted']
    assert result.json()['data']['deleted'] == 2 and Supplier.objects.count() == 2
    repeated = execute(admin_client, planned['preview_token'])
    assert repeated.status_code == 200 and repeated['Idempotency-Replayed'] == 'true' and repeated.json() == result.json()
    assert OperationLog.objects.filter(resource='cg_suppliers', action='delete').count() == 2


def test_bulk_permissions_rechecked_and_foreign_records_never_leak(admin_client, admin_user, member_user):
    member, role = restricted(member_user)
    foreign = Supplier.objects.create(code='SECRET', name='private', creator=admin_user)
    own = Supplier.objects.create(code='OWN', name='mine', creator=member_user)
    result = preview(member, foreign, own)
    assert [item['status'] for item in result['items']] == ['unavailable', 'ready']
    assert 'SECRET' not in str(result) and 'private' not in str(result)
    assert execute(admin_client, result['preview_token']).status_code == 400
    RolePermission.objects.filter(role=role, permission__code='cg_suppliers:delete').delete()
    assert execute(member, result['preview_token']).status_code == 403
    assert Supplier.objects.count() == 2


def test_bulk_tamper_expiry_and_missing_idempotency_key(admin_client, admin_user, monkeypatch):
    row = Supplier.objects.create(code='A', name='Item', creator=admin_user)
    token = preview(admin_client, row)['preview_token']
    assert execute(admin_client, token + 'tampered').status_code == 400
    assert admin_client.post(ROOT + 'bulk-delete/', {'preview_token': token, 'confirmation': '删除选中记录'}, format='json').status_code == 400
    from django.core.signing import TimestampSigner
    monkeypatch.setattr(TimestampSigner, 'unsign', lambda *args, **kwargs: (_ for _ in ()).throw(signing.SignatureExpired()))
    assert execute(admin_client, token).status_code == 400 and Supplier.objects.count() == 1


def test_decimal_range_and_approval_locks_are_preserved(admin_client, admin_user):
    from apps.cg_orders.models import PurchaseOrder
    if not any(field.name == 'approval_status' for field in PurchaseOrder._meta.fields):
        pytest.skip('当前生成定义未启用审批字段')
    supplier = Supplier.objects.create(code='money', name='甲', creator=admin_user)
    first = PurchaseOrder.objects.create(code='LOW', supplier=supplier, amount='0.10', creator=admin_user)
    second = PurchaseOrder.objects.create(code='HIGH', supplier=supplier, amount='1000.01', creator=admin_user, approval_status='pending')
    root = '/api/v1/cg-orders/records/'
    response = admin_client.get(root, {'advanced': json.dumps(definition(condition('amount', 'gte', '0.11'))['advanced'])})
    assert response.status_code == 200, response.content
    assert [row['id'] for row in response.json()['data']['items']] == [str(second.pk)]
    previewed = admin_client.post(root + 'bulk-preview/', {'selection': selection(first, second)}, format='json').json()['data']
    assert [item['status'] for item in previewed['items']] == ['ready', 'blocked']
    PurchaseOrder.objects.filter(pk=first.pk).update(approval_status='pending')
    result = admin_client.post(root + 'bulk-delete/', {'preview_token': previewed['preview_token'], 'confirmation': '删除选中记录'}, format='json', HTTP_IDEMPOTENCY_KEY='approval-lock')
    assert result.status_code == 200 and result.json()['data']['deleted'] == 0
    assert result.json()['data']['items'][0]['status'] == 'conflict' and PurchaseOrder.objects.count() == 2


def test_duplicate_selection_and_schema_drift_are_rejected(admin_client, admin_user, monkeypatch):
    from apps.cg_suppliers.schema import SCHEMA
    row = Supplier.objects.create(code='schema', name='甲', creator=admin_user)
    assert admin_client.post(ROOT + 'bulk-preview/', {'selection': selection(row, row)}, format='json').status_code == 400
    token = preview(admin_client, row)['preview_token']
    own = save(admin_client).json()['data']
    monkeypatch.setitem(SCHEMA, 'title', '新版供应商')
    assert execute(admin_client, token).status_code == 400
    views = admin_client.get(ROOT + 'query-views/').json()['data']
    assert views['items'][0]['id'] == own['id'] and views['items'][0]['available'] is False


@pytest.mark.parametrize('value', [[], [{'id': 'bad', 'version': 1}], [{'id': str(uuid4()), 'version': True}],
    [{'id': str(uuid4()), 'version': 1}] * 101])
def test_bulk_selection_bounds(admin_client, value):
    assert admin_client.post(ROOT + 'bulk-preview/', {'selection': value}, format='json').status_code == 400


@pytest.mark.django_db(transaction=True)
def test_postgres_duplicate_bulk_execution_has_one_effect():
    if connection.vendor != 'postgresql':
        pytest.skip('真实PostgreSQL并发检查')
    user = get_user_model().objects.create_superuser('bulk-concurrent', password='Unused#12345')
    row = Supplier.objects.create(code='concurrent', name='Item', creator=user)
    client = APIClient(); client.force_authenticate(user)
    token = preview(client, row)['preview_token']; barrier = Barrier(2)
    def run():
        close_old_connections()
        try:
            local = APIClient(); local.force_authenticate(get_user_model().objects.get(pk=user.pk))
            barrier.wait(timeout=10)
            response = execute(local, token)
            return response.status_code, response.json()
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]
    assert results[0] == results[1] and results[0][0] == 200
    assert Supplier.objects.count() == 0 and OperationLog.objects.filter(resource='cg_suppliers', action='delete').count() == 1


@pytest.mark.django_db(transaction=True)
def test_postgres_opposite_bulk_orders_do_not_deadlock(monkeypatch):
    if connection.vendor != 'postgresql':
        pytest.skip('真实PostgreSQL并发检查')
    users = [get_user_model().objects.create_superuser('bulk-order-' + str(index), password='Unused#12345')
             for index in range(2)]
    rows = [Supplier.objects.create(code='order-' + str(index), name='Item', creator=users[0])
            for index in range(2)]
    tokens = []
    for user, selected in zip(users, (rows, list(reversed(rows)))):
        client = APIClient(); client.force_authenticate(user)
        tokens.append((user.pk, preview(client, *selected)['preview_token']))

    from apps.core.codegen.runtime import GeneratedService
    original_visible = GeneratedService.visible
    barrier = Barrier(2)
    request_thread = local()

    def synchronized_visible(service, actor):
        queryset = original_visible(service, actor)
        if not getattr(request_thread, 'synchronized', False):
            request_thread.synchronized = True
            barrier.wait(timeout=10)
        return queryset

    monkeypatch.setattr(GeneratedService, 'visible', synchronized_visible)

    def run(user_id, token, expected_ids):
        close_old_connections()
        try:
            user = get_user_model().objects.get(pk=user_id)
            client = APIClient(); client.force_authenticate(user)
            lock_sql = []
            def capture_sql(execute_sql, sql, params, many, context):
                if 'FOR UPDATE' in sql.upper() and 'CG_SUPPLIERS_SUPPLIER' in sql.upper():
                    lock_sql.append(sql)
                return execute_sql(sql, params, many, context)
            with connection.execute_wrapper(capture_sql):
                response = execute(client, token)
            payload = response.json()
            return response.status_code, payload, lock_sql, expected_ids
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        expected = [[str(row.pk) for row in rows], [str(row.pk) for row in reversed(rows)]]
        futures = [pool.submit(run, user_id, token, ids) for (user_id, token), ids in zip(tokens, expected)]
        results = [future.result(timeout=30) for future in futures]
    assert [status for status, _, _, _ in results] == [200, 200], results
    for _, payload, lock_sql, expected_ids in results:
        assert [item['id'] for item in payload['data']['items']] == expected_ids
        canonical = [sql.upper() for sql in lock_sql if ' IN ' in sql.upper() and ' ORDER BY ' in sql.upper()]
        assert canonical, lock_sql
        assert ('ORDER BY 1 ASC' in canonical[0]
                or 'ORDER BY "CG_SUPPLIERS_SUPPLIER"."ID" ASC' in canonical[0])
    assert Supplier.objects.count() == 0
    assert OperationLog.objects.filter(resource='cg_suppliers', action='delete').count() == 2
