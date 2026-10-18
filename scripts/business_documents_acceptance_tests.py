"""真实生成主子表模块的整单导入验收；运行于隔离生成模块测试配置。"""
import csv
import io
import json
import uuid
from dataclasses import replace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook
from rest_framework.test import APIClient

from apps.cg_orders import extensions
from apps.cg_orders.models import PurchaseOrder, PurchaseLine, PurchaseNote
from apps.cg_orders.schema import SCHEMA
from apps.cg_suppliers.models import Supplier
from apps.core import modules
from apps.core.models import Tenant, TenantMembership
from apps.core.tenancy import tenant_context
from apps.data_io.tasks import run_data_import
from apps.permissions.models import Role, Permission, RolePermission, UserRole
from apps.tasks.models import TaskRecord, ImportRowReceipt, ImportExecution

pytestmark = pytest.mark.django_db
ROOT = '/api/v1/data-io/business/'
HEADERS = ['code', 'supplier', 'status', 'lines.product', 'lines.quantity', 'lines.price', 'notes.content']
OPTIONS = {'mapping': dict(zip(HEADERS, HEADERS)), 'key': 'code', 'mode': 'create'}


@pytest.fixture(autouse=True)
def explicitly_registered(monkeypatch):
    # 独立验收也可使用登记条件升级前保存的生成副本；生产模块仍必须显式声明。
    monkeypatch.setattr(modules, 'MODULES', tuple(replace(item, data_io_resources=('cg_orders',))
        if item.key == 'cg_orders' else item for item in modules.MODULES))


@pytest.fixture
def supplier(admin_user):
    return Supplier.objects.create(code='S', name='授权供应商', creator=admin_user)


def rows(supplier, *, key='A', quantity='2'):
    return [[key, str(supplier.pk), 'draft', '甲', quantity, '3.00', '备注'],
            [key, str(supplier.pk), 'draft', '乙', '1', '4.50', '']]


def source(data, *, xlsx=False):
    stream = io.BytesIO()
    if xlsx:
        book = Workbook(); sheet = book.active
        for row in [HEADERS, *data]:
            sheet.append(row)
        book.save(stream); book.close()
        return SimpleUploadedFile('documents.xlsx', stream.getvalue())
    text = io.StringIO(); writer = csv.writer(text); writer.writerows([HEADERS, *data])
    return SimpleUploadedFile('documents.csv', text.getvalue().encode('utf-8-sig'))


def preview(client, data, *, mode='create', xlsx=False, options=None):
    result = client.post(ROOT + 'preview/', {'resource': 'cg_orders', 'file': source(data, xlsx=xlsx),
        'options': json.dumps(options or {**OPTIONS, 'mode': mode})}, format='multipart')
    assert result.status_code == 200, result.content
    return result.json()['data']


def submit(client, plan):
    result = client.post(ROOT + f"plans/{plan['id']}/submit/")
    assert result.status_code == 200, result.content
    return result.json()['data']


def execute(client, plan):
    task = submit(client, plan); run_data_import(task['id'])
    return TaskRecord.objects.get(pk=task['id'])


def restricted(user, *, hidden=None):
    fields = [field['name'] for field in SCHEMA['fields']]
    for group in SCHEMA['details']:
        fields.extend([group['name'], *(group['name'] + '.' + field['name'] for field in group['fields'])])
    fields = [name for name in fields if name != hidden]
    role = Role.objects.create(name='整单导入员-' + uuid.uuid4().hex[:8], field_permissions={'cg_orders': {'read': fields, 'write': fields}})
    UserRole.objects.create(user=user, role=role)
    for code in ['cg_orders:read', 'cg_orders:create', 'cg_orders:update', 'cg_suppliers:read', 'data_io:import', 'data_io:export', 'task:retry']:
        resource, action = code.split(':')
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'resource': resource, 'action': action, 'name': code})
        RolePermission.objects.create(role=role, permission=permission)
    client = APIClient(); client.force_authenticate(user)
    return client, role


@pytest.mark.parametrize('xlsx', [False, True])
def test_whole_document_preview_confirm_idempotence_and_multiple_groups(admin_client, supplier, xlsx):
    data = rows(supplier)
    data += rows(supplier, key='B')[:1]
    plan = preview(admin_client, data, xlsx=xlsx)
    assert plan['summary'] == dict(total=2, created=2, updated=0, skipped=0, failed=0, source_rows=3)
    assert not PurchaseOrder.objects.exists()
    task = submit(admin_client, plan); assert submit(admin_client, plan)['id'] == task['id']
    run_data_import(task['id']); run_data_import(task['id'])
    record = TaskRecord.objects.get(pk=task['id'])
    assert record.status == 'success' and record.result['created'] == 2 and record.result['source_rows'] == 3
    assert list(ImportRowReceipt.objects.order_by('row').values_list('row', flat=True)) == [2, 4]
    order = PurchaseOrder.objects.get(code='A')
    assert list(order.lines.values_list('product', flat=True)) == ['甲', '乙']
    assert list(order.notes.values_list('content', flat=True)) == ['备注']


@pytest.mark.parametrize('failure', ['bad_detail', 'inconsistent_main', 'blank_key', 'no_detail'])
def test_invalid_group_never_partially_writes_and_errors_expand_all_source_rows(admin_client, supplier, failure):
    data = rows(supplier)
    if failure == 'bad_detail': data[1][4] = '0'
    if failure == 'inconsistent_main': data[1][2] = 'confirmed'
    if failure == 'blank_key':
        for row in data: row[0] = ''
    if failure == 'no_detail':
        for row in data: row[3:6] = ['', '', '']
    plan = preview(admin_client, data)
    assert plan['summary']['created'] == 0 and plan['summary']['failed'] == (2 if failure == 'blank_key' else 1)
    errors = admin_client.get(ROOT + f"plans/{plan['id']}/errors/")
    assert errors.status_code == 200, errors.content
    parsed = list(csv.reader(io.StringIO(errors.content.decode('utf-8-sig'))))
    assert parsed[0] == ['source_row', 'error_code', *HEADERS]
    assert [row[0] for row in parsed[1:]] == ['2', '3']
    execute(admin_client, plan)
    assert PurchaseOrder.objects.count() == PurchaseLine.objects.count() == PurchaseNote.objects.count() == 0


def test_one_failed_document_does_not_cancel_other_document_and_runtime_extension_is_atomic(admin_client, supplier, monkeypatch):
    plan = preview(admin_client, rows(supplier) + rows(supplier, key='B'))
    def after_save(*, instance, **kwargs):
        if instance.code == 'A':
            from rest_framework.exceptions import ValidationError
            assert instance.lines.count() == 2
            raise ValidationError('业务规则拒绝整单')
    monkeypatch.setattr(extensions, 'after_save', after_save)
    record = execute(admin_client, plan)
    assert record.status == 'success' and record.result['failed'] == record.result['created'] == 1
    assert list(PurchaseOrder.objects.values_list('code', flat=True)) == ['B']
    assert PurchaseLine.objects.count() == 2 and PurchaseNote.objects.count() == 1
    errors = admin_client.get(ROOT + f'import/{record.pk}/errors/')
    assert len(list(csv.reader(io.StringIO(errors.content.decode('utf-8-sig'))))) == 3


def test_replace_details_and_stale_preview_preserves_entire_old_document(admin_client, supplier):
    execute(admin_client, preview(admin_client, rows(supplier)))
    order = PurchaseOrder.objects.get(); old_children = list(order.lines.values_list('pk', flat=True))
    data = rows(supplier)[:1]; data[0][3] = '更新商品'
    plan = preview(admin_client, data, mode='update')
    PurchaseOrder.objects.filter(pk=order.pk).update(version=order.version + 1)
    record = execute(admin_client, plan)
    assert record.result['failed'] == 1 and record.result['errors'][0]['message'] == 'record_changed'
    assert list(order.lines.values_list('pk', flat=True)) == old_children
    record = execute(admin_client, preview(admin_client, data, mode='update'))
    assert record.result['updated'] == 1
    assert list(order.lines.values_list('product', flat=True)) == ['更新商品']
    assert not order.lines.filter(pk__in=old_children).exists()


def test_omitted_optional_group_explicitly_clears_it(admin_client, supplier):
    execute(admin_client, preview(admin_client, rows(supplier)))
    options = {**OPTIONS, 'mode': 'update', 'mapping': {key: value for key, value in OPTIONS['mapping'].items() if key != 'notes.content'}}
    record = execute(admin_client, preview(admin_client, rows(supplier), options=options))
    assert record.result['updated'] == 1 and not PurchaseNote.objects.exists()


def test_catalog_requires_complete_detail_read_write_and_rechecks_after_preview(admin_client, member_user, supplier):
    client, role = restricted(member_user, hidden='lines.price')
    assert client.get(ROOT + 'catalog/', {'resource': 'cg_orders'}).status_code == 403
    plan = preview(admin_client, rows(supplier))
    # 预检归属不可转移，自己的完整权限预检后撤销明细字段。
    client, full_role = restricted(member_user)
    role.is_active = False; role.save()
    plan = preview(client, rows(supplier))
    full_role.field_permissions['cg_orders']['write'].remove('lines.price'); full_role.save()
    assert client.post(ROOT + f"plans/{plan['id']}/submit/").status_code == 403
    assert not PurchaseOrder.objects.exists()


def test_required_detail_mapping_and_group_limit_enforced(admin_client, supplier):
    options = {**OPTIONS, 'mapping': {key: value for key, value in OPTIONS['mapping'].items() if key != 'lines.quantity'}}
    result = admin_client.post(ROOT + 'preview/', {'resource': 'cg_orders', 'file': source(rows(supplier)), 'options': json.dumps(options)}, format='multipart')
    assert result.status_code == 400
    plan = preview(admin_client, rows(supplier)[:1] * 101)
    assert plan['summary']['failed'] == 1 and not PurchaseOrder.objects.exists()


def test_related_record_scope_rechecked_before_any_detail_write(admin_client, member_user, supplier):
    client, role = restricted(member_user)
    plan = preview(client, rows(supplier))
    assert plan['summary']['failed'] == 1
    assert not PurchaseOrder.objects.exists()


def test_relation_deleted_after_preview_is_rechecked_before_document_write(admin_client, supplier):
    plan = preview(admin_client, rows(supplier))
    assert plan['summary']['created'] == 1
    supplier.delete()
    record = execute(admin_client, plan)
    assert record.result['failed'] == 1 and record.result['created'] == 0
    assert not PurchaseOrder.objects.exists() and not PurchaseLine.objects.exists()


def test_approval_locked_document_rejected_during_preview_and_at_execution(admin_client, supplier):
    if not SCHEMA.get('approval'):
        pytest.skip('仅对带审批定义的真实生成模块执行')
    execute(admin_client, preview(admin_client, rows(supplier)))
    order = PurchaseOrder.objects.get()
    PurchaseOrder.objects.filter(pk=order.pk).update(approval_status='pending')
    plan = preview(admin_client, rows(supplier), mode='update')
    assert plan['errors'] == [{'row': 2, 'message': 'approval_locked'}]
    PurchaseOrder.objects.filter(pk=order.pk).update(approval_status='draft')
    plan = preview(admin_client, rows(supplier), mode='update')
    PurchaseOrder.objects.filter(pk=order.pk).update(approval_status='approved')
    record = execute(admin_client, plan)
    assert record.result['failed'] == 1
    order.refresh_from_db(); assert order.version == 1 and order.lines.count() == 2


def test_master_detail_catalog_reports_import_only(admin_client):
    result = admin_client.get(ROOT + 'catalog/', {'resource': 'cg_orders'})
    assert result.status_code == 200, result.content
    data = result.json()['data']
    assert data['structure'] == 'master_detail' and data['exportable'] is True
    assert {'lines.product', 'notes.content'} <= {item['name'] for item in data['fields']}
    assert admin_client.get(ROOT + 'export/', {'resource': 'cg_orders'}).status_code == 400


@pytest.mark.parametrize('revoked', ['tenant', 'membership'])
def test_background_rechecks_tenant_lifecycle_and_membership(settings, member_user, revoked):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    tenant = Tenant.objects.create(name='整单租户', slug='documents')
    membership = TenantMembership.objects.create(tenant=tenant, user=member_user)
    with tenant_context(tenant.pk):
        client, _ = restricted(member_user)
    client.credentials(HTTP_X_ADMINCORE_TENANT=str(tenant.pk))
    with tenant_context(tenant.pk):
        supplier = Supplier.objects.create(code='S', name='本租户', creator=member_user)
    plan = preview(client, rows(supplier)); task = submit(client, plan)
    if revoked == 'tenant':
        tenant.status = Tenant.STATUS_SUSPENDED; tenant.save()
    else:
        membership.is_active = False; membership.save()
    run_data_import(task['id'])
    record = TaskRecord.all_objects.get(pk=task['id'])
    assert record.status == 'failed' and not PurchaseOrder.all_objects.exists()


def test_background_enters_batch_tenant_and_stamps_all_children(admin_client, admin_user, settings):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    own = Tenant.objects.create(name='甲', slug='own-documents')
    other = Tenant.objects.create(name='乙', slug='other-documents')
    with tenant_context(own.pk):
        supplier = Supplier.objects.create(code='S', name='甲', creator=admin_user)
    admin_client.credentials(**{**admin_client._credentials, 'HTTP_X_ADMINCORE_TENANT': str(own.pk)})
    plan = preview(admin_client, rows(supplier)); task = submit(admin_client, plan)
    with tenant_context(None):
        run_data_import(task['id'])
    assert PurchaseOrder.all_objects.get().tenant_id == own.pk
    assert set(PurchaseLine.all_objects.values_list('tenant_id', flat=True)) == {own.pk}
    assert not PurchaseOrder.all_objects.filter(tenant=other).exists()


def test_noncontiguous_groups_keep_source_rows_and_skip_whole_document(admin_client, supplier):
    data = rows(supplier)
    plan = preview(admin_client, [data[0], *rows(supplier, key='B')[:1], data[1]])
    assert plan['summary']['total'] == 2
    record = execute(admin_client, plan)
    assert record.result['created'] == 2 and PurchaseOrder.objects.get(code='A').lines.count() == 2
    before = list(PurchaseLine.objects.values_list('pk', flat=True))
    record = execute(admin_client, preview(admin_client, data, mode='skip'))
    assert record.result['skipped'] == 1 and record.result['processed'] == 1
    assert list(PurchaseLine.objects.values_list('pk', flat=True)) == before


def test_crash_resume_keeps_committed_document_and_retries_entire_failed_document(admin_client, supplier, monkeypatch):
    calls = []
    def crash(**kwargs):
        calls.append(kwargs['instance'].code)
        if kwargs['instance'].code == 'B':
            assert kwargs['instance'].lines.count() == 2
            raise RuntimeError('worker stopped after child writes')
    monkeypatch.setattr(extensions, 'after_save', crash)
    task = submit(admin_client, preview(admin_client, rows(supplier) + rows(supplier, key='B')))
    with pytest.raises(RuntimeError):
        run_data_import(task['id'])
    assert list(PurchaseOrder.objects.values_list('code', flat=True)) == ['A']
    assert PurchaseLine.objects.count() == 2 and ImportRowReceipt.objects.count() == 1
    monkeypatch.setattr(extensions, 'after_save', lambda **kwargs: calls.append(kwargs['instance'].code))
    result = admin_client.post('/api/v1/data-io/import/' + task['id'] + '/')
    assert result.status_code == 202, result.content
    run_data_import(result.json()['data']['id'])
    record = TaskRecord.objects.get(pk=result.json()['data']['id'])
    assert record.result['created'] == record.result['processed'] == 2
    assert calls == ['A', 'B', 'B'] and PurchaseLine.objects.count() == 4
    assert ImportExecution.objects.get(pk=task['id']).batch_id == ImportExecution.objects.get(pk=record.pk).batch_id


def test_field_revocation_between_documents_preserves_completed_whole_document(member_user, monkeypatch):
    client, role = restricted(member_user)
    supplier = Supplier.objects.create(code='S', name='自己的供应商', creator=member_user)
    def revoke(**kwargs):
        role.field_permissions['cg_orders']['write'].remove('lines.price'); role.save()
    monkeypatch.setattr(extensions, 'after_save', revoke)
    record = execute(client, preview(client, rows(supplier) + rows(supplier, key='B')))
    assert record.status == 'failed' and record.result['created'] == record.result['processed'] == 1
    assert list(PurchaseOrder.objects.values_list('code', flat=True)) == ['A']
    assert PurchaseLine.objects.count() == 2 and PurchaseNote.objects.count() == 1


def test_foreign_tenant_main_relation_and_detail_file_never_write(admin_client, admin_user, settings):
    from apps.files.models import FileModel
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    own = Tenant.objects.create(name='本租户', slug='document-references-own')
    other = Tenant.objects.create(name='其他租户', slug='document-references-other')
    with tenant_context(other.pk):
        foreign = Supplier.objects.create(code='S', name='其他租户', creator=admin_user)
        evidence = FileModel.objects.create(original_name='foreign.txt', file='fixture/foreign.txt', uploader=admin_user)
    with tenant_context(own.pk):
        supplier = Supplier.objects.create(code='S', name='本租户', creator=admin_user)
    admin_client.credentials(**{**admin_client._credentials, 'HTTP_X_ADMINCORE_TENANT': str(own.pk)})
    assert preview(admin_client, rows(foreign))['summary']['failed'] == 1
    data = rows(supplier)
    # 可将任意源列映射为附件；只需要授权的 ID，不接受跨租户文件。
    data[0][6] = str(evidence.pk); data[1][6] = ''
    options = {**OPTIONS, 'mapping': {**OPTIONS['mapping'], 'notes.content': 'lines.evidence'}}
    plan = preview(admin_client, data, options=options)
    assert plan['summary']['failed'] == 1
    execute(admin_client, plan)
    assert not PurchaseOrder.all_objects.exists() and not PurchaseLine.all_objects.exists()
