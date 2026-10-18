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


def test_snapshot_pins_main_and_detail_files_across_withdraw_and_replacement(admin_client, admin_user, business):
    from apps.files.models import FileModel
    from apps.approvals.models import ApprovalFileReference
    from apps.files.references import is_referenced
    files = [FileModel.objects.create(original_name='审批附件', file=f'test/snapshot-{i}.txt', uploader=admin_user) for i in range(3)]
    row = business(); url = URL + row['id'] + '/'
    changed = admin_client.patch(url, {'version': 1, 'attachment': str(files[0].pk), 'lines': [
        {'product': '同一文件去重', 'quantity': 1, 'price': '1.00', 'evidence': str(files[0].pk)},
        {'product': '明细独立文件', 'quantity': 1, 'price': '1.00', 'evidence': str(files[1].pk)}]}, format='json')
    assert changed.status_code == 200, changed.content
    row = changed.json()['data']; pending = submit(admin_client, row)
    assert pending.status_code == 200, pending.content
    assert submit(admin_client, row).json() == pending.json()
    application = ApprovalRequest.objects.get()
    assert set(application.file_references.values_list('file_id', flat=True)) == {files[0].pk, files[1].pk}
    snapshot = application.business_snapshot
    cancelled = admin_client.post(URL + row['id'] + '/withdraw/', {'version': 3}, format='json')
    assert cancelled.status_code == 200, cancelled.content
    replaced = admin_client.patch(url, {'version': 4, 'attachment': str(files[2].pk),
        'lines': [{'product': '已替换', 'quantity': 1, 'price': '1.00'}]}, format='json')
    assert replaced.status_code == 200, replaced.content
    assert all(is_referenced(file) for file in files)
    for file in files:
        assert admin_client.delete(f'/api/v1/files/{file.pk}/').status_code == 409
    assert ApprovalRequest.objects.get(pk=application.pk).business_snapshot == snapshot
    # 继续提交只新增本次快照的引用；上次历史不被改写。
    assert submit(admin_client, replaced.json()['data']).status_code == 200
    assert ApprovalFileReference.objects.count() == 3


@pytest.mark.parametrize('failure', ['unavailable', 'audit'])
def test_failed_attachment_submission_creates_no_snapshot_reference(admin_client, admin_user, business, failure):
    from apps.files.models import FileModel
    from apps.approvals.models import ApprovalFileReference
    file = FileModel.objects.create(original_name='快照事务', file='test/rollback.txt', uploader=admin_user)
    row = business(); PurchaseOrder.objects.filter(pk=row['id']).update(attachment=file)
    if failure == 'unavailable':
        # 模拟升级前已经被回收的附件，提交时必须重新验证。
        FileModel.objects.filter(pk=file.pk).update(is_deleted=True)
        result = submit(admin_client, row)
        assert result.status_code == 400, result.content
    else:
        with patch('apps.cg_orders.services.write_audit', side_effect=RuntimeError('audit unavailable')):
            assert submit(admin_client, row).status_code == 500
    assert not ApprovalFileReference.objects.exists() and not ApprovalRequest.objects.exists()
    restored = PurchaseOrder.objects.get(pk=row['id'])
    assert restored.version == 1 and restored.approval_status == 'draft'


def test_submit_rechecks_revoked_file_acl(admin_client, member_client, member_user, admin_user, business):
    from apps.files.models import FileModel, FileAccessGrant
    from apps.permissions.models import Permission, RolePermission
    file = FileModel.objects.create(original_name='撤销授权附件', file='test/revoked.txt', uploader=admin_user)
    row = business(); PurchaseOrder.objects.filter(pk=row['id']).update(attachment=file, creator=member_user)
    role = Role.objects.create(name='业务提交与文件读取')
    UserRole.objects.create(role=role, user=member_user)
    for code in ['cg_orders:submit', 'cg_orders:read', 'file:read']:
        resource, action = code.split(':')
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'name': code, 'resource': resource, 'action': action})
        RolePermission.objects.create(role=role, permission=permission)
    grant = FileAccessGrant.objects.create(file=file, user=member_user)
    grant.is_active = False; grant.save(update_fields=['is_active'])
    result = submit(member_client, row)
    assert result.status_code == 400, result.content
    assert not ApprovalRequest.objects.exists()


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


def test_business_snapshot_and_report_respect_current_viewer_field_policy(admin_client, member_user, business):
    from apps.approvals.serializers import ApprovalRequestSerializer
    from apps.permissions.models import Permission, RolePermission
    from rest_framework.test import APIRequestFactory
    row = business('1000.00'); submit(admin_client, row)
    role = Role.objects.create(name='restricted-reviewer', field_permissions={'cg_orders': {
        'read': ['code', 'lines', 'lines.product'], 'write': []}})
    UserRole.objects.create(user=member_user, role=role)
    permission = Permission.objects.create(name='read order', resource='cg_orders', action='read', code='cg_orders:read')
    RolePermission.objects.create(role=role, permission=permission)
    request = APIRequestFactory().get('/'); request.user = member_user
    application = ApprovalRequest.objects.get()
    data = ApprovalRequestSerializer(application, context={'request': request}).data
    assert data['extra_data'] == {} and '1000.00' not in str(data['business_snapshot'])
    assert '采购项目' in str(data['business_snapshot']) and row['code'] not in application.title
    with pytest.raises(PermissionError):
        execute_definition(member_user, {'data_source': 'cg_orders', 'dimensions': [{'field': 'approval_status'}], 'metric': {'field': 'amount', 'aggregation': 'sum'}})


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


def purchase_board():
    query = {'data_source': 'cg_orders', 'chart_type': 'bar', 'dimensions': [{'field': 'approval_status'}],
             'metrics': [{'key': 'm_amount', 'label': '采购金额', 'field': 'amount', 'aggregation': 'sum'},
                         {'key': 'm_count', 'label': '订单数', 'field': 'id', 'aggregation': 'count'}]}
    return {'schema_version': 2, 'widgets': [
        {'key': 'status', 'title': '审批状态', 'span': 6, 'definition': query},
        {'key': 'total', 'title': '采购总额', 'span': 6, 'definition': {**query, 'dimensions': []}},
    ], 'filters': [{'key': 'category', 'label': '采购类别', 'operator': 'eq', 'value': 'office',
                    'bindings': [{'widget': 'status', 'field': 'category'}, {'widget': 'total', 'field': 'category'}]}],
        'links': [{'source': 'status', 'source_field': 'approval_status', 'target': 'total', 'target_field': 'approval_status'}]}


def test_purchase_board_exact_metrics_scope_tenant_and_revoke(admin_user, member_user, business, settings):
    from apps.reports.dashboards import run_design, design_details
    from apps.permissions.models import Permission, RolePermission
    from apps.core.models import Tenant
    from apps.core.tenancy import tenant_context
    role = Role.objects.create(name='board-reader')
    UserRole.objects.create(role=role, user=member_user)
    permission = Permission.objects.create(name='board-order-read', code='cg_orders:read', resource='cg_orders', action='read')
    RolePermission.objects.create(role=role, permission=permission)
    one = business('0.10','B1'); two = business('0.20','B2')
    PurchaseOrder.objects.filter(pk=one['id']).update(creator=member_user)
    board = purchase_board()
    assert run_design(member_user, board)['widgets'][1]['result']['rows'] == [{'m_amount': '0.10', 'm_count': 1}]
    details = design_details(member_user, board, {'widget': 'total'})
    assert details['columns'] == ['id','amount'] and len(details['rows']) == 1
    assert str(details['rows'][0]['id']) == one['id'] and details['rows'][0]['amount'] == '0.10'
    a = Tenant.objects.create(name='BoardA',slug='board-a'); b = Tenant.objects.create(name='BoardB',slug='board-b')
    PurchaseOrder.objects.filter(pk=one['id']).update(tenant=a)
    PurchaseOrder.objects.filter(pk=two['id']).update(tenant=b)
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    with tenant_context(a.pk): assert run_design(admin_user, board)['widgets'][1]['result']['rows'] == [{'m_amount': '0.10', 'm_count': 1}]
    with tenant_context(b.pk): assert run_design(admin_user, board)['widgets'][1]['result']['rows'] == [{'m_amount': '0.20', 'm_count': 1}]
    settings.ADMINCORE_MULTI_TENANT_ENABLED = False
    role.field_permissions = {'cg_orders': {'read': ['category'], 'write': []}}; role.save()
    with pytest.raises(PermissionError): run_design(member_user, board)
    with pytest.raises(PermissionError): design_details(member_user, board, {'widget': 'total'})
    role.field_permissions = {}; role.is_active = False; role.save()
    with pytest.raises(PermissionError): run_design(member_user, board)


@pytest.mark.parametrize('grain,expected', [('day','2026-01-01'),('week','2025-12-29'),('month','2026-01-01'),('quarter','2026-01-01'),('year','2026-01-01')])
def test_purchase_date_bucket_timezone_and_details(admin_user, business, grain, expected):
    from datetime import datetime, timezone
    from django.utils.timezone import override
    from apps.reports.services import drill_down
    row = business()
    PurchaseOrder.objects.filter(pk=row['id']).update(created_at=datetime(2025,12,31,16,30,tzinfo=timezone.utc))
    query = {**purchase_board()['widgets'][0]['definition'], 'dimensions': [{'field': 'created_at','grain': grain}]}
    with override('Asia/Shanghai'):
        result = execute_definition(admin_user,query)
        assert result['rows'][0]['created_at'].isoformat() == expected
        assert result['rows'][0]['m_amount'] == '0.10'
        assert len(drill_down(admin_user,query,{'created_at': expected})['rows']) == 1


def test_business_return_locks_record_repeats_review_and_finalizes_once(admin_client, member_user, business):
    row = business('1000.00')
    pending = submit(admin_client, row).json()['data']
    request_id = pending['approval_request']
    reviewer = APIClient(); reviewer.force_authenticate(member_user)
    first = reviewer.post(f'/api/v1/approvals/{request_id}/approve/', {}, format='json')
    assert first.status_code == 200 and first.json()['data']['current_node'] == 'review'
    version = first.json()['data']['workflow_version']
    returned = admin_client.post(f'/api/v1/approvals/{request_id}/return-node/', {
        'target_node': 'finance', 'expected_workflow_version': version, 'comment': '复核采购金额'}, format='json')
    assert returned.status_code == 200, returned.content
    assert returned.json()['data']['current_node'] == 'finance'
    record = PurchaseOrder.objects.get(pk=row['id'])
    assert record.approval_status == 'pending' and record.version == 2
    assert admin_client.patch(URL + row['id'] + '/', {'version': 2, 'remarks': '改原始业务'}, format='json').status_code == 409
    assert reviewer.post(f'/api/v1/approvals/{request_id}/approve/', {'expected_workflow_version': version}, format='json').status_code == 409
    moved = reviewer.post(f'/api/v1/approvals/{request_id}/approve/', {
        'expected_workflow_version': returned.json()['data']['workflow_version']}, format='json')
    assert moved.status_code == 200, moved.content
    final = admin_client.post(f'/api/v1/approvals/{request_id}/approve/', {
        'expected_workflow_version': moved.json()['data']['workflow_version']}, format='json', HTTP_IDEMPOTENCY_KEY='return-business-final')
    assert final.status_code == 200, final.content
    replay = admin_client.post(f'/api/v1/approvals/{request_id}/approve/', {
        'expected_workflow_version': moved.json()['data']['workflow_version']}, format='json', HTTP_IDEMPOTENCY_KEY='return-business-final')
    assert replay['Idempotency-Replayed'] == 'true'
    record.refresh_from_db()
    assert record.approval_status == 'approved' and record.version == 3
    assert ApprovalRequest.objects.get(pk=request_id).steps.count() == 4


def test_generated_business_uses_current_published_revision(admin_client, admin_user, business):
    first = business('0.10', code='PO-old-release')
    old_pending = submit(admin_client, first).json()['data']
    flow = ApprovalRequest.objects.get(pk=old_pending['approval_request']).flow
    draft = admin_client.post(f'/api/v1/approvals/flows/{flow.pk}/new-revision/', {}, format='json').json()['data']
    assert admin_client.post(f"/api/v1/approvals/flows/{draft['id']}/publish/", {'version': draft['version']}, format='json').status_code == 200
    second = business('0.10', code='PO-new-release')
    new_pending = submit(admin_client, second).json()['data']
    assert ApprovalRequest.objects.get(pk=new_pending['approval_request']).flow_id == __import__('uuid').UUID(draft['id'])
    assert ApprovalRequest.objects.get(pk=old_pending['approval_request']).flow_id == flow.pk
    assert admin_client.post(f"/api/v1/approvals/{old_pending['approval_request']}/approve/", {}, format='json').status_code == 200


def test_approval_mutation_response_redacts_business_fields(admin_client, member_user, business):
    from apps.permissions.models import Permission, RolePermission
    row = business('1000.00')
    pending = submit(admin_client, row).json()['data']
    role = Role.objects.create(name='limited-approval', field_permissions={'cg_orders': {'read': ['code'], 'write': []}})
    UserRole.objects.create(user=member_user, role=role)
    permission = Permission.objects.create(name='读取订单', resource='cg_orders', action='read', code='cg_orders:read')
    RolePermission.objects.create(role=role, permission=permission)
    reviewer = APIClient(); reviewer.force_authenticate(member_user)
    response = reviewer.post(f"/api/v1/approvals/{pending['approval_request']}/approve/", {}, format='json')
    assert response.status_code == 200, response.content
    data = response.json()['data']
    assert data['extra_data'] == {} and '1000.00' not in str(data['business_snapshot'])
