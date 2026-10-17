"""仅由 validate_codegen_v2.py 在独立配置下运行。"""
from decimal import Decimal
from unittest.mock import patch
import uuid
import pytest
from apps.cg_suppliers.models import Supplier
from apps.cg_categories.models import Category
from apps.cg_orders.models import PurchaseOrder, PurchaseLine
from apps.cg_orders import extensions
from apps.core.models import DataDictionary, Tenant
from apps.core.tenancy import tenant_context
from apps.logs.models import OperationLog
from apps.permissions.models import Role, Permission, RolePermission, UserRole

pytestmark = pytest.mark.django_db
SUPPLIERS = '/api/v1/cg-suppliers/records/'
ORDERS = '/api/v1/cg-orders/records/'
CATEGORIES = '/api/v1/cg-categories/records/'


def order(supplier_record, **changes):
    return {'code': 'PO-1', 'supplier': str(supplier_record.pk), 'version': 0, 'due_date': '2026-12-30',
            'ordered_at': '2026-10-18T12:00:00+08:00', 'status': 'draft', 'category': 'office',
            'attachment': None, 'remarks': '', 'lines': [{'product': '电脑', 'quantity': 2, 'price': '0.10'},
                                                       {'product': '显示器', 'quantity': 3, 'price': '0.20'}], 'notes': [], **changes}


@pytest.fixture(autouse=True)
def dictionary():
    DataDictionary.objects.create(code='purchase_category', name='采购类别', items=[{'value': 'office', 'label': '办公', 'is_active': True}])


@pytest.fixture
def supplier(admin_user):
    return Supplier.objects.create(code='S-1', name='供应商一', creator=admin_user)


@pytest.fixture(autouse=True)
def calculate_total(monkeypatch):
    def before_save(*, actor, instance, values, details):
        lines = details.get('lines')
        if lines is not None:
            values['amount'] = sum((Decimal(line['price']) * line['quantity'] for line in lines), Decimal('0'))
    monkeypatch.setattr(extensions, 'before_save', before_save)


def test_real_money_detail_transaction_idempotency_and_version(admin_client, supplier):
    first = admin_client.post(ORDERS, order(supplier), format='json', HTTP_IDEMPOTENCY_KEY='v2-order')
    assert first.status_code == 201, first.content
    repeated = admin_client.post(ORDERS, order(supplier), format='json', HTTP_IDEMPOTENCY_KEY='v2-order')
    assert first.json() == repeated.json()
    data = first.json()['data']; assert data['amount'] == '0.80' and len(data['lines']) == 2
    assert PurchaseOrder.objects.count() == 1 and PurchaseLine.objects.count() == 2
    url = ORDERS + data['id'] + '/'
    assert admin_client.patch(url, {'version': 0, 'remarks': 'stale'}, format='json').status_code == 409
    updated = admin_client.patch(url, {'version': 1, 'lines': [{'product': '新商品', 'quantity': 1, 'price': '1.01'}]}, format='json')
    assert updated.status_code == 200, updated.content
    assert updated.json()['data']['amount'] == '1.01' and PurchaseLine.objects.count() == 1
    assert admin_client.patch(url, {'version': 2, 'remarks': '仅改主表'}, format='json').status_code == 200
    assert PurchaseLine.objects.count() == 1
    assert OperationLog.objects.filter(resource='cg_orders').count() == 3
    assert all('电脑' not in str(row.after_values) for row in OperationLog.objects.filter(resource='cg_orders'))


def test_detail_and_audit_errors_roll_back_whole_order(admin_client, supplier):
    with patch('apps.cg_orders.services.write_audit', side_effect=RuntimeError('audit failure')):
        assert admin_client.post(ORDERS, order(supplier), format='json').status_code == 500
    assert not PurchaseOrder.objects.exists() and not PurchaseLine.objects.exists()
    response = admin_client.post(ORDERS, order(supplier), format='json'); identifier = response.json()['data']['id']
    with patch.object(extensions, 'after_save', side_effect=RuntimeError('business failure')):
        assert admin_client.patch(ORDERS + identifier + '/', {'version': 1, 'lines': [{'product': 'replacement', 'quantity': 1, 'price': '2'}]}, format='json').status_code == 500
    assert PurchaseOrder.objects.get().version == 1 and PurchaseLine.objects.count() == 2


@pytest.mark.parametrize('changes', [
    {'amount': '999'}, {'creator': 'spoof'}, {'version': 1}, {'status': 'unknown'}, {'category': 'missing'},
    {'lines': []}, {'lines': [{'product': 'x', 'quantity': 1, 'price': 0.1}]},
    {'lines': [{'product': 'x', 'quantity': 0, 'price': '1'}]},
    {'lines': [{'product': 'x', 'quantity': 1, 'price': '1.001'}]},
    {'lines': [{'product': 'x', 'quantity': 1, 'price': '1', 'parent': 'spoof'}]},
    {'supplier': str(uuid.uuid4())}, {'attachment': str(uuid.uuid4())}, {'due_date': '2026-02-30'},
])
def test_runtime_rejects_invalid_values(admin_client, supplier, changes):
    response = admin_client.post(ORDERS, order(supplier, **changes), format='json')
    assert response.status_code in {400, 409}, response.content
    assert not PurchaseOrder.objects.exists()


def grant(user, resource, *actions):
    role = Role.objects.create(name='generated-' + resource)
    UserRole.objects.create(user=user, role=role)
    for action in actions:
        permission = Permission.objects.create(name=resource + ':' + action, resource=resource, action=action, code=resource + ':' + action)
        RolePermission.objects.create(role=role, permission=permission)


def test_reference_choices_and_writes_require_target_permission_and_scope(member_client, member_user, admin_user, supplier):
    grant(member_user, 'cg_orders', 'read', 'create', 'update')
    response = member_client.get(ORDERS + 'choices/', {'field': 'supplier'})
    assert response.status_code == 403
    assert member_client.post(ORDERS, order(supplier), format='json').status_code == 403
    grant(member_user, 'cg_suppliers', 'read')
    mine = Supplier.objects.create(code='mine', name='本人供应商', creator=member_user)
    options = member_client.get(ORDERS + 'choices/', {'field': 'supplier'}).json()['data']['items']
    assert [item['value'] for item in options] == [str(mine.pk)]
    assert member_client.post(ORDERS, order(supplier), format='json').status_code == 400
    response = member_client.post(ORDERS, order(mine), format='json')
    assert response.status_code == 201, response.content
    assert member_client.get(ORDERS).json()['data']['pagination']['total'] == 1
    foreign = PurchaseOrder.objects.create(creator=admin_user, code='other', supplier=supplier)
    assert member_client.get(ORDERS + str(foreign.pk) + '/').status_code == 404


def test_filters_ordering_and_unique_constraints(admin_client, supplier):
    assert admin_client.post(ORDERS, order(supplier), format='json').status_code == 201
    assert admin_client.post(ORDERS, order(supplier), format='json').status_code in {400, 409}
    response = admin_client.get(ORDERS, {'amount_min': '0.79', 'amount_max': '0.81', 'status': 'draft', 'ordering': '-amount'})
    assert response.status_code == 200 and response.json()['data']['pagination']['total'] == 1, response.content
    assert admin_client.get(ORDERS, {'amount_min': '1.00'}).json()['data']['pagination']['total'] == 0
    listed = admin_client.get(ORDERS, {'ordering': '-created_at,-id'}).json()['data']['items']
    assert listed[0]['display_labels']['supplier'] == supplier.name
    assert 'lines' not in listed[0] and 'notes' not in listed[0]
    for query in [{'amount_min': 'NaN'}, {'status': 'invalid'}, {'due_date_min': '2026-02-30'}, {'ordering': 'supplier__name'}, {'unknown': '1'}]:
        assert admin_client.get(ORDERS, query).status_code == 400


def test_tree_move_cycle_and_protected_delete(admin_client):
    root = admin_client.post(CATEGORIES, {'code': 'root', 'name': '根', 'rank': 1, 'version': 0}, format='json')
    assert root.status_code == 201, root.content
    root_id = root.json()['data']['id']
    child = admin_client.post(CATEGORIES, {'code': 'child', 'name': '子', 'rank': 2, 'version': 0, 'parent': root_id}, format='json')
    assert child.status_code == 201, child.content
    child_id = child.json()['data']['id']
    assert admin_client.patch(CATEGORIES + root_id + '/', {'version': 1, 'parent': child_id}, format='json').status_code == 400
    assert admin_client.patch(CATEGORIES + root_id + '/', {'version': 1, 'parent': root_id}, format='json').status_code == 400
    assert admin_client.delete(CATEGORIES + root_id + '/', {'version': 1}, format='json').status_code == 409
    assert admin_client.get(CATEGORIES, {'parent': 'root'}).json()['data']['pagination']['total'] == 1
    assert admin_client.get(CATEGORIES, {'parent': root_id}).json()['data']['pagination']['total'] == 1
    assert admin_client.patch(CATEGORIES + child_id + '/', {'version': 1, 'parent': None}, format='json').status_code == 200
    assert Category.objects.get(pk=child_id).parent_id is None


def test_cross_tenant_references_and_unique_codes(admin_user, admin_client, settings):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    first, second = Tenant.objects.create(slug='cg-one', name='一'), Tenant.objects.create(slug='cg-two', name='二')
    with tenant_context(first.pk):
        supplier = Supplier.objects.create(code='same', name='一', creator=admin_user)
    with tenant_context(second.pk):
        Supplier.objects.create(code='same', name='二', creator=admin_user)
    response = admin_client.post(ORDERS, order(supplier, category=''), format='json', HTTP_X_ADMINCORE_TENANT=str(second.pk))
    assert response.status_code == 400, response.content


def test_attachment_acl_and_dictionary_disable(member_client, member_user, admin_user, supplier):
    from apps.files.models import FileModel
    grant(member_user, 'cg_orders', 'read', 'create')
    grant(member_user, 'cg_suppliers', 'read')
    grant(member_user, 'file', 'read')
    mine = Supplier.objects.create(creator=member_user, code='mine', name='本人')
    file = FileModel.objects.create(original_name='private.txt', file='fixture/private.txt', uploader=admin_user)
    assert member_client.post(ORDERS, order(mine, attachment=str(file.pk)), format='json').status_code == 400
    file.uploader = member_user; file.save()
    assert member_client.post(ORDERS, order(mine, attachment=str(file.pk)), format='json').status_code == 201
    DataDictionary.objects.filter(code='purchase_category').update(is_active=False)
    assert member_client.post(ORDERS, order(mine, code='PO-2'), format='json').status_code == 400


def test_choice_queries_validate_and_paginate_authorized_rows(admin_client, supplier):
    for query in [{'field': 'code'}, {'field': 'supplier', 'page': '0'}, {'field': 'supplier', 'page': 'x'},
                  {'field': 'supplier', 'extra': 'no'}, {'field': 'supplier', 'q': 'x' * 201}]:
        assert admin_client.get(ORDERS + 'choices/', query).status_code == 400
    options = admin_client.get(ORDERS + 'choices/', {'field': 'category', 'q': '办公'}).json()['data']
    assert options == {'items': [{'value': 'office', 'label': '办公'}], 'has_more': False}
    assert admin_client.get(ORDERS + 'choices/', {'field': 'supplier', 'q': '不存在'}).json()['data']['items'] == []
    Supplier.objects.bulk_create([Supplier(code='page-' + str(i), name='分页 ' + str(i), creator=supplier.creator) for i in range(60)])
    first = admin_client.get(ORDERS + 'choices/', {'field': 'supplier', 'q': '分页'}).json()['data']
    second = admin_client.get(ORDERS + 'choices/', {'field': 'supplier', 'q': '分页', 'page': 2}).json()['data']
    assert len(first['items']) == 50 and first['has_more'] and len(second['items']) == 10 and not second['has_more']
    assert not {row['value'] for row in first['items']} & {row['value'] for row in second['items']}
    root = Category.objects.create(code='root', name='根节点', creator=supplier.creator)
    assert admin_client.get(CATEGORIES + 'choices/', {'field': 'parent'}).json()['data']['items'][0]['value'] == str(root.pk)
    assert admin_client.get(CATEGORIES, {'parent': 'invalid'}).status_code == 400
    assert admin_client.patch(CATEGORIES + str(root.pk) + '/', {'name': 'missing version'}, format='json').status_code == 400
    assert admin_client.delete(CATEGORIES + str(root.pk) + '/', {'version': 1}, format='json').status_code == 200


def test_bad_registered_reference_definitions_are_controlled(admin_user):
    from apps.core.codegen.runtime import reference_queryset
    from rest_framework.exceptions import ValidationError
    for module, model, label in [('not_enabled', 'Missing', 'name'), ('cg_suppliers', 'Missing', 'name'),
                                  ('cg_orders', 'PurchaseLine', 'product'), ('cg_suppliers', 'Supplier', 'created_at')]:
        with pytest.raises(ValidationError):
            reference_queryset({'kind': 'relation', 'target': {'module': module, 'model': model, 'label': label}}, admin_user)


def test_revoked_reference_labels_are_not_disclosed(member_client, member_user, supplier):
    grant(member_user, 'cg_orders', 'read', 'create')
    grant(member_user, 'cg_suppliers', 'read')
    mine = Supplier.objects.create(code='mine', name='撤权后应隐藏', creator=member_user)
    response = member_client.post(ORDERS, order(mine), format='json')
    assert response.status_code == 201
    identifier = response.json()['data']['id']
    RolePermission.objects.filter(permission__code='cg_suppliers:read').delete()
    detail = member_client.get(ORDERS + identifier + '/').json()['data']
    assert detail['display_labels']['supplier'] == ''
    assert member_client.get(ORDERS + 'choices/', {'field': 'supplier'}).status_code == 403
    assert member_client.get(ORDERS + 'choices/', {'field': 'attachment'}).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_postgres_optimistic_concurrency_and_tree_cycle():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.contrib.auth import get_user_model
    from django.db import connection, close_old_connections
    from rest_framework.test import APIClient
    if connection.vendor != 'postgresql':
        pytest.skip('真实行锁与并发只在PostgreSQL验收')
    actors = [get_user_model().objects.create_superuser('concurrent' + str(i), password='Fixture#12345') for i in range(2)]
    first = Category.objects.create(code='a', name='A', creator=actors[0])
    second = Category.objects.create(code='b', name='B', creator=actors[0])
    barrier = Barrier(2)
    def move(index):
        close_old_connections()
        client = APIClient(); client.force_authenticate(get_user_model().objects.get(pk=actors[index].pk))
        source, target = (first, second) if index == 0 else (second, first)
        barrier.wait(timeout=10)
        try:
            return client.patch(CATEGORIES + str(source.pk) + '/', {'version': 1, 'parent': str(target.pk)}, format='json').status_code
        finally:
            close_old_connections()
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(move, range(2))) == [200, 400]
    first.refresh_from_db(); second.refresh_from_db()
    target = first if first.parent_id is None else second
    barrier = Barrier(2)
    def edit(index):
        close_old_connections()
        client = APIClient(); client.force_authenticate(get_user_model().objects.get(pk=actors[index].pk))
        barrier.wait(timeout=10)
        try:
            return client.patch(CATEGORIES + str(target.pk) + '/', {'version': target.version, 'name': 'edited' + str(index)}, format='json').status_code
        finally:
            close_old_connections()
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(edit, range(2))) == [200, 409]
