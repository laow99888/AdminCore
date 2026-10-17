"""由隔离生成验收器安装真实采购模块后执行。"""
import json
import os
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch
import pytest
from rest_framework.test import APIClient
from apps.cg_orders.models import PurchaseOrder
from apps.cg_orders import extensions
from apps.cg_suppliers.models import Supplier
from apps.approvals.models import ApprovalFlow, ApprovalRequest
from apps.core.models import DataDictionary
from apps.permissions.models import Role, UserRole
from apps.reports.services import catalog_for, execute_definition

pytestmark = pytest.mark.django_db
URL = '/api/v1/cg-orders/records/'


@pytest.fixture
def business(admin_client, admin_user, member_user, monkeypatch):
    folder = Path(os.environ['ADMINCORE_INTEGRATION_EXAMPLES'])
    flow = json.loads((folder / 'purchase-flow.json').read_text(encoding='utf-8'))
    for key, username, user in [('finance', '财务', member_user), ('review', '主管', admin_user)]:
        role = Role.objects.create(name=username)
        UserRole.objects.create(role=role, user=user)
        next(n for n in flow['nodes'] if n['id'] == key)['assignee']['role_id'] = str(role.pk)
    ApprovalFlow.objects.create(name='采购审批', code='purchase-approval', status='published', definition=flow, created_by=admin_user)
    DataDictionary.objects.create(code='purchase_category', name='采购类别', items=[{'value': 'office', 'label': '办公'}])
    supplier = Supplier.objects.create(code='S1', name='采购供应商', creator=admin_user)
    def before_save(*, actor, instance, values, details):
        if 'lines' in details:
            values['amount'] = sum((line['quantity'] * Decimal(line['price']) for line in details['lines']), Decimal('0'))
    monkeypatch.setattr(extensions, 'before_save', before_save)
    def create(price='0.10', code='PO-1'):
        response = admin_client.post(URL, {'version': 0, 'code': code, 'supplier': str(supplier.pk),
            'due_date': '2026-12-30', 'ordered_at': '2026-10-18T12:00:00+08:00', 'status': 'draft',
            'category': 'office', 'attachment': None, 'remarks': '',
            'lines': [{'product': '采购项目', 'quantity': 1, 'price': price}], 'notes': []}, format='json')
        assert response.status_code == 201, response.content
        return response.json()['data']
    return create


def submit(client, row, **extra):
    return client.post(URL + row['id'] + '/submit/', {'version': row['version'], **extra}, format='json', HTTP_IDEMPOTENCY_KEY='submit-' + row['id'] + '-' + str(row['version']))


def test_low_order_snapshot_approval_and_report(admin_client, admin_user, business):
    row = business('0.10')
    pending = submit(admin_client, row); assert pending.status_code == 200, pending.content
    data = pending.json()['data']; assert data['approval_status'] == 'pending' and data['version'] == 2
    replay = submit(admin_client, row); assert replay.json() == pending.json()
    assert ApprovalRequest.objects.count() == 1
    application = ApprovalRequest.objects.get(); assert application.current_node == 'review'
    assert application.extra_data == {'amount': '0.10'}
    assert '采购项目' in str(application.business_snapshot)
    url = URL + row['id'] + '/'
    assert admin_client.patch(url, {'version': 2, 'remarks': '篡改'}, format='json').status_code == 409
    assert admin_client.delete(url, {'version': 2}, format='json').status_code == 409
    approved = admin_client.post(f'/api/v1/approvals/{application.pk}/approve/', format='json')
    assert approved.status_code == 200, approved.content
    record = PurchaseOrder.objects.get(); assert record.approval_status == 'approved' and record.version == 3
    assert admin_client.patch(url, {'version': 3, 'remarks': '改审批结果'}, format='json').status_code == 409
    assert submit(admin_client, {'id': row['id'], 'version': 3}).status_code == 409
    assert any(source['key'] == 'cg_orders' for source in catalog_for(admin_user))
    design = {'data_source': 'cg_orders', 'dimensions': [{'field': 'approval_status'}], 'metric': {'field': 'amount', 'aggregation': 'sum'}}
    report = execute_definition(admin_user, design)
    assert report['rows'] == [{'approval_status': 'approved', 'value': '0.10'}]


def test_high_order_two_levels_and_central_cancel_sync(admin_client, member_user, business):
    row = business('1000.00'); response = submit(admin_client, row); assert response.status_code == 200, response.content
    application = ApprovalRequest.objects.get(); assert application.current_node == 'finance'
    client = APIClient(); client.force_authenticate(member_user)
    moved = client.post(f'/api/v1/approvals/{application.pk}/approve/', format='json')
    assert moved.status_code == 200 and moved.json()['data']['current_node'] == 'review'
    assert PurchaseOrder.objects.get().approval_status == 'pending'
    result = admin_client.post(f'/api/v1/approvals/{application.pk}/cancel/', format='json')
    assert result.status_code == 200
    order = PurchaseOrder.objects.get(); assert order.approval_status == 'cancelled' and order.version == 3
    assert not application.steps.filter(status='pending').exists()
    assert submit(admin_client, {'id': row['id'], 'version': 3}).status_code == 200
    assert ApprovalRequest.objects.count() == 2


def test_business_withdraw_reject_edit_resubmit(admin_client, business):
    row = business(); pending = submit(admin_client, row).json()['data']
    response = admin_client.post(URL + row['id'] + '/withdraw/', {'version': 2}, format='json')
    assert response.status_code == 200, response.content
    assert response.json()['data']['approval_status'] == 'cancelled'
    assert ApprovalRequest.objects.get().status == 'cancelled'
    updated = admin_client.patch(URL + row['id'] + '/', {'version': 3, 'lines': [{'product': '新行', 'quantity': 1, 'price': '2.01'}]}, format='json')
    assert updated.status_code == 200 and updated.json()['data']['approval_status'] == 'draft'
    response = submit(admin_client, updated.json()['data']); assert response.status_code == 200
    application = ApprovalRequest.objects.get(pk=response.json()['data']['approval_request'])
    assert admin_client.post(f'/api/v1/approvals/{application.pk}/reject/', format='json').status_code == 200
    record = PurchaseOrder.objects.get(); assert record.approval_status == 'rejected' and record.version == 6
    assert record.amount == Decimal('2.01')
    assert admin_client.post(f'/api/v1/approvals/{pending["approval_request"]}/approve/', format='json').status_code == 400


def test_failed_sync_rolls_back_decision_and_steps(admin_client, business):
    row = business(); pending = submit(admin_client, row).json()['data']
    with patch('apps.cg_orders.services.write_audit', side_effect=RuntimeError('audit unavailable')):
        result = admin_client.post(f'/api/v1/approvals/{pending["approval_request"]}/approve/', format='json')
        assert result.status_code == 500
    assert PurchaseOrder.objects.get().approval_status == 'pending'
    application = ApprovalRequest.objects.get(); assert application.status == 'pending'
    assert application.steps.get().status == 'pending'


def test_submission_rejects_forged_context_and_archived_flow(admin_client, business):
    row = business()
    assert submit(admin_client, row, extra_data={'amount': '0'}, approval_status='approved').status_code == 400
    assert not ApprovalRequest.objects.exists()
    ApprovalFlow.objects.update(status='archived')
    assert submit(admin_client, row).status_code == 400
    assert PurchaseOrder.objects.get().version == 1 and not ApprovalRequest.objects.exists()


def test_report_respects_business_permission_and_self_scope(admin_client, member_user, admin_user, business, settings):
    from apps.permissions.models import Permission, RolePermission
    from apps.reports.validators import validate_definition
    from rest_framework.exceptions import ValidationError
    row = business('0.10')
    assert not any(source['key'] == 'cg_orders' for source in catalog_for(member_user))
    design = {'data_source': 'cg_orders', 'dimensions': [], 'metric': {'field': 'amount', 'aggregation': 'sum'}}
    with pytest.raises(PermissionError): execute_definition(member_user, design)
    role = Role.objects.create(name='采购读取')
    UserRole.objects.create(role=role, user=member_user)
    permission = Permission.objects.create(name='订单读取', code='cg_orders:read', resource='cg_orders', action='read')
    RolePermission.objects.create(role=role, permission=permission)
    assert execute_definition(member_user, design)['rows'] == [{'value': None}]
    PurchaseOrder.objects.filter(pk=row['id']).update(creator=member_user)
    assert execute_definition(member_user, design)['rows'] == [{'value': '0.10'}]
    with pytest.raises(ValidationError):
        validate_definition({**design, 'filters': [{'field': 'amount', 'operator': 'gte', 'value': 0.1}]})
    with pytest.raises(ValidationError):
        validate_definition({**design, 'dimensions': [{'field': 'supplier__name'}]})
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'cg_orders')
    assert not any(source['key'] == 'cg_orders' for source in catalog_for(admin_user))
    with pytest.raises(ValidationError): execute_definition(admin_user, design)


@pytest.mark.django_db(transaction=True)
def test_postgres_approval_withdraw_race_has_one_consistent_result(admin_client, admin_user, business):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import connection, close_old_connections
    if connection.vendor != 'postgresql': pytest.skip('需要真实行锁')
    row = business(); pending = submit(admin_client, row).json()['data']
    barrier = Barrier(2)
    def act(operation):
        close_old_connections()
        client = APIClient(); client.force_authenticate(admin_user)
        try:
            barrier.wait(timeout=10)
            return (client.post(f'/api/v1/approvals/{pending["approval_request"]}/approve/', format='json') if operation == 'approve'
                    else client.post(URL + row['id'] + '/withdraw/', {'version': 2}, format='json')).status_code
        finally: close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(act, ['approve', 'withdraw']))
    assert results.count(200) == 1 and set(results) <= {200, 400, 409}
    application = ApprovalRequest.objects.get(); record = PurchaseOrder.objects.get()
    assert record.approval_status == application.status and record.version == 3
    assert not application.steps.filter(status='pending').exists()


def test_tenant_selection_and_report_exclude_other_tenant(admin_user, business, settings):
    from apps.core.models import Tenant
    from apps.core.tenancy import tenant_context
    create = business
    first = create('0.10', 'one'); second = create('0.20', 'two')
    a = Tenant.objects.create(slug='tenant-a', name='A'); b = Tenant.objects.create(slug='tenant-b', name='B')
    PurchaseOrder.objects.filter(pk=first['id']).update(tenant=a)
    PurchaseOrder.objects.filter(pk=second['id']).update(tenant=b)
    design = {'data_source': 'cg_orders', 'dimensions': [], 'metric': {'field': 'amount', 'aggregation': 'sum'}}
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    with tenant_context(a.pk):
        assert execute_definition(admin_user, design)['rows'] == [{'value': '0.10'}]
    with tenant_context(b.pk):
        assert execute_definition(admin_user, design)['rows'] == [{'value': '0.20'}]
