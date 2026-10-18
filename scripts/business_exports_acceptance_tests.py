"""真实生成业务模块的后台整单导出：快照、当前授权、取消与失联恢复。"""
import csv
import io
from dataclasses import replace
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Barrier

import pytest
from django.utils import timezone
from django.db import connection, connections, transaction
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.core import modules
from apps.core.models import OutboxEvent, Tenant, TenantMembership, DataScopeGrant
from apps.auth_app.models import AuthSession
from apps.core.tasks import dispatch_outbox
from apps.core.tenancy import tenant_context
from apps.cg_orders.models import PurchaseOrder, PurchaseLine, PurchaseNote
from apps.cg_orders.schema import SCHEMA
from apps.cg_suppliers.models import Supplier
from apps.data_io import business_export as exporter
from apps.data_io.models import BusinessExportRequest
from apps.permissions.models import Role, UserRole, Permission, RolePermission
from apps.tasks.models import TaskRecord

pytestmark = pytest.mark.django_db
ROOT = '/api/v1/data-io/business/exports/'


@pytest.fixture(autouse=True)
def registered(monkeypatch):
    monkeypatch.setattr(modules, 'MODULES', tuple(replace(item, data_io_resources=('cg_orders',))
        if item.key == 'cg_orders' else item for item in modules.MODULES))


@pytest.fixture
def document(admin_user):
    supplier = Supplier.objects.create(code='S', name='供应商', creator=admin_user)
    row = PurchaseOrder.objects.create(code='A', supplier=supplier, status='draft', creator=admin_user)
    PurchaseLine.objects.create(parent=row, position=0, product='甲', quantity=2, price='3.00')
    PurchaseLine.objects.create(parent=row, position=1, product='乙', quantity=1, price='4.50')
    PurchaseNote.objects.create(parent=row, position=0, content='备注')
    return row


def submit(client, *, format='csv', filters=None):
    result = client.post(ROOT, {'resource': 'cg_orders', 'format': format, 'filters': filters or {}}, format='json')
    assert result.status_code == 202, result.content
    return result.json()['data']['id']


def execute(client, **kwargs):
    identifier = submit(client, **kwargs)
    exporter.run_business_export(identifier)
    record = TaskRecord.objects.get(pk=identifier)
    return record


def download(client, identifier):
    return client.get(ROOT + str(identifier) + '/download/')


def member(client_user, *, hidden=None):
    fields = [field['name'] for field in SCHEMA['fields']]
    for group in SCHEMA['details']:
        fields.extend([group['name'], *(group['name'] + '.' + field['name'] for field in group['fields'])])
    role = Role.objects.create(name='导出员', field_permissions={
        'cg_orders': {'read': [name for name in fields if name != hidden], 'write': []}})
    DataScopeGrant.objects.create(role=role, resource='cg_orders', scope='all')
    UserRole.objects.create(user=client_user, role=role)
    for code in ['cg_orders:read', 'data_io:export', 'task:read', 'task:cancel']:
        resource, action = code.split(':')
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'resource': resource, 'action': action, 'name': code})
        RolePermission.objects.create(role=role, permission=permission)
    client = APIClient(); client.force_authenticate(client_user)
    return client, role


@pytest.mark.parametrize('format', ['csv', 'xlsx'])
def test_whole_document_export_aligns_details_without_cross_join(admin_client, document, format):
    record = execute(admin_client, format=format)
    assert record.status == 'success', record.error
    assert record.result['documents'] == 1 and record.result['rows'] == 2
    result = download(admin_client, record.pk)
    assert result.status_code == 200, result.content
    assert result['Cache-Control'] == 'private, no-store'
    if format == 'csv':
        values = list(csv.reader(io.StringIO(result.content.decode('utf-8-sig'))))
    else:
        book = load_workbook(io.BytesIO(result.content), read_only=True)
        try:
            values = [list(row) for row in book.active.values]
        finally:
            book.close()
    headers = values.pop(0)
    assert [row[headers.index('code')] for row in values] == ['A', 'A']
    assert [row[headers.index('lines.product')] for row in values] == ['甲', '乙']
    assert values[0][headers.index('notes.content')] == '备注'
    assert values[1][headers.index('notes.content')] in ('', None)
    assert not ('artifact' in admin_client.get(ROOT + str(record.pk) + '/').json()['data'])
    exporter.run_business_export(str(record.pk))
    record.refresh_from_db(); assert record.status == 'success'


def test_read_only_export_needs_no_create_or_import_permission(member_user, document):
    client, role = member(member_user, hidden='lines.price')
    record = execute(client)
    assert record.status == 'success', record.error
    result = download(client, record.pk)
    assert result.status_code == 200
    assert 'lines.price' not in result.content.decode('utf-8-sig').splitlines()[0]


@pytest.mark.parametrize('when', ['before', 'after'])
@pytest.mark.parametrize('change', ['version', 'child', 'scope', 'field', 'session', 'permission'])
def test_current_record_and_authorization_rechecked(member_user, document, when, change):
    client, role = member(member_user)
    identifier = submit(client)
    if when == 'after':
        exporter.run_business_export(identifier)
        assert TaskRecord.objects.get(pk=identifier).status == 'success'
    if change == 'version':
        PurchaseOrder.objects.filter(pk=document.pk).update(version=2)
    elif change == 'child':
        PurchaseLine.objects.filter(parent=document, position=0).update(product='新值')
    elif change == 'scope':
        DataScopeGrant.objects.filter(role=role, resource='cg_orders').update(scope='self')
    elif change == 'field':
        role.field_permissions['cg_orders']['read'].remove('lines.price'); role.save()
    elif change == 'session':
        member_user.session_version += 1; member_user.save()
    else:
        RolePermission.objects.filter(role=role, permission__code='data_io:export').delete()
    if when == 'before':
        exporter.run_business_export(identifier)
        record = TaskRecord.objects.get(pk=identifier)
        # 未改变主版本的受支持写入之外的子行变动，在导出前取当前值；产物发布后会验摘要。
        assert record.status == ('success' if change == 'child' else 'failed'), record.error
    else:
        assert download(client, identifier).status_code in (400, 401, 403)


def test_filters_and_snapshot_do_not_add_new_rows(admin_client, document):
    identifier = submit(admin_client, filters={'code': 'A'})
    PurchaseOrder.objects.create(code='B', supplier=document.supplier, status='draft', creator=document.creator)
    exporter.run_business_export(identifier)
    record = TaskRecord.objects.get(pk=identifier)
    assert record.status == 'success' and record.result['documents'] == 1
    assert admin_client.post(ROOT, {'resource': 'cg_orders', 'format': 'csv', 'filters': {'page': '1'}}, format='json').status_code == 400


def test_other_owner_and_tenant_cannot_download(admin_client, member_user, document, settings):
    record = execute(admin_client)
    client, _ = member(member_user)
    assert download(client, record.pk).status_code == 404
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    tenant = Tenant.objects.create(slug='other-export', name='别的租户')
    result = admin_client.get(ROOT + str(record.pk) + '/download/', HTTP_X_ADMINCORE_TENANT=str(tenant.pk))
    assert result.status_code == 404


def test_cancel_between_batches_has_no_published_artifact(admin_client, document, monkeypatch):
    identifier = submit(admin_client)
    original = exporter.guarded_batch
    def cancel_after_read(*args, **kwargs):
        result = original(*args, **kwargs)
        TaskRecord.objects.get(pk=identifier).mark_cancelled()
        return result
    monkeypatch.setattr(exporter, 'guarded_batch', cancel_after_read)
    exporter.run_business_export(identifier)
    record = TaskRecord.objects.get(pk=identifier)
    assert record.status == 'cancelled'
    assert not BusinessExportRequest.objects.get(pk=identifier).artifact
    assert download(admin_client, identifier).status_code == 400


def test_running_export_can_be_cancelled_via_task_center(admin_client, document, monkeypatch):
    identifier = submit(admin_client)
    TaskRecord.objects.get(pk=identifier).mark_started()
    monkeypatch.setattr('config.celery.app.control.revoke', lambda *args, **kwargs: None)
    result = admin_client.post('/api/v1/tasks/' + identifier + '/cancel/')
    assert result.status_code == 200, result.content
    assert TaskRecord.objects.get(pk=identifier).status == 'cancelled'


def test_outbox_dispatch_carries_policy_and_exhausts_bounded_attempts(admin_client, document, monkeypatch):
    identifier = submit(admin_client)
    calls = []
    monkeypatch.setattr(exporter.run_business_export, 'apply_async', lambda **kwargs: calls.append(kwargs))
    dispatch_outbox()
    execution = BusinessExportRequest.objects.get(pk=identifier)
    assert calls[0]['task_id'] == identifier
    assert calls[0]['time_limit'] == execution.policy['hard_timeout']
    event = OutboxEvent.objects.get(topic='export.requested', payload__record_id=identifier)
    event.status = 'failed'; event.attempts = execution.policy['dispatch_attempts']; event.save()
    dispatch_outbox()
    assert TaskRecord.objects.get(pk=identifier).error == 'dispatch_attempts_exhausted'


def test_lost_worker_queue_expiry_and_artifact_expiry(admin_client, document):
    identifier = submit(admin_client)
    TaskRecord.objects.filter(pk=identifier).update(created_at=timezone.now() - timedelta(days=2))
    exporter.recover_lost_exports()
    assert TaskRecord.objects.get(pk=identifier).status == 'failed'
    identifier = submit(admin_client)
    TaskRecord.objects.get(pk=identifier).mark_started()
    TaskRecord.objects.filter(pk=identifier).update(started_at=timezone.now() - timedelta(days=2))
    exporter.recover_lost_exports()
    assert TaskRecord.objects.get(pk=identifier).status == 'failed'
    record = execute(admin_client)
    BusinessExportRequest.objects.filter(pk=record.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert download(admin_client, record.pk).status_code == 400
    exporter.recover_lost_exports()
    assert not BusinessExportRequest.objects.get(pk=record.pk).artifact


@pytest.mark.parametrize('limit', ['MAX_DOCUMENTS', 'MAX_ROWS', 'MAX_BYTES'])
@pytest.mark.parametrize('format', ['csv', 'xlsx'])
def test_bounded_export_rejects_over_budget(admin_client, document, monkeypatch, limit, format):
    monkeypatch.setattr(exporter, limit, 0)
    result = admin_client.post(ROOT, {'resource': 'cg_orders', 'format': format}, format='json')
    if limit == 'MAX_DOCUMENTS':
        assert result.status_code == 400
    else:
        assert result.status_code == 202
        exporter.run_business_export(result.json()['data']['id'])
        execution = BusinessExportRequest.objects.get(pk=result.json()['data']['id'])
        assert execution.record.status == 'failed' and not execution.artifact


def test_empty_snapshot_still_rechecks_revoked_user(admin_client, admin_user):
    identifier = submit(admin_client)
    admin_user.session_version += 1; admin_user.save()
    exporter.run_business_export(identifier)
    assert TaskRecord.objects.get(pk=identifier).status == 'failed'


@pytest.mark.parametrize('when', ['before', 'after'])
def test_original_device_revocation_cannot_be_bypassed_by_another_device(admin_client, admin_user, document, when):
    identifier = submit(admin_client)
    execution = BusinessExportRequest.objects.get(pk=identifier)
    assert execution.session_id is not None
    if when == 'after':
        exporter.run_business_export(identifier)
        assert TaskRecord.objects.get(pk=identifier).status == 'success'
    AuthSession.objects.filter(pk=execution.session_id).update(revoked_at=timezone.now())
    another_device = APIClient(); another_device.force_authenticate(admin_user)
    if when == 'before':
        exporter.run_business_export(identifier)
        assert TaskRecord.objects.get(pk=identifier).status == 'failed'
    else:
        assert download(another_device, identifier).status_code == 403


@pytest.mark.parametrize('change', ['membership', 'tenant'])
@pytest.mark.parametrize('when', ['before', 'after'])
def test_tenant_reclamation_rechecked_in_worker_and_download(member_user, document, settings, when, change):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    tenant = Tenant.objects.create(slug='export-tenant', name='导出租户')
    membership = TenantMembership.objects.create(user=member_user, tenant=tenant)
    PurchaseOrder.all_objects.filter(pk=document.pk).update(tenant=tenant)
    with tenant_context(tenant.pk):
        client, _ = member(member_user)
    client.credentials(HTTP_X_ADMINCORE_TENANT=str(tenant.pk))
    identifier = submit(client)
    if when == 'after':
        exporter.run_business_export(identifier)
        assert TaskRecord.all_objects.get(pk=identifier).status == 'success'
    if change == 'membership':
        membership.is_active = False; membership.save()
    else:
        tenant.status = Tenant.STATUS_SUSPENDED; tenant.save()
    if when == 'before':
        exporter.run_business_export(identifier)
        assert TaskRecord.all_objects.get(pk=identifier).status == 'failed'
    else:
        assert download(client, identifier).status_code == 403


def test_artifact_tampering_and_cleanup(admin_client, document, django_capture_on_commit_callbacks):
    record = execute(admin_client)
    execution = BusinessExportRequest.objects.get(pk=record.pk)
    storage, name = execution.artifact.storage, execution.artifact.name
    assert storage.exists(name)
    with storage.open(name, 'wb') as stream:
        stream.write(b'changed artifact')
    assert download(admin_client, record.pk).status_code == 400
    with django_capture_on_commit_callbacks(execute=True):
        record.delete()
    assert not storage.exists(name)


def postgres_only():
    if connection.vendor != 'postgresql':
        pytest.skip('行锁并发必须在真实 PostgreSQL 验证')


def in_thread(call):
    try:
        return call()
    finally:
        connections.close_all()


@pytest.mark.django_db(transaction=True)
def test_postgres_duplicate_deliveries_publish_once(admin_client, document, monkeypatch):
    postgres_only()
    # transaction=True 会真实提交，不能让测试环境 eager 回调在线程启动前抢先执行。
    # 保留已提交 outbox，下面两个线程执行真实任务实现和数据库行锁。
    monkeypatch.setattr('apps.core.events._dispatch_after_commit', lambda: None)
    identifier = submit(admin_client)
    barrier = Barrier(2)
    original, writes = exporter.write_artifact, []
    def track(*args):
        writes.append(1)
        return original(*args)
    monkeypatch.setattr(exporter, 'write_artifact', track)
    def delivery():
        barrier.wait(10)
        return exporter.run_business_export(identifier)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(in_thread, delivery) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]
    assert len(writes) == 1 and sum(result.get('skipped', False) for result in results) == 1
    assert TaskRecord.objects.get(pk=identifier).status == 'success'
    assert download(admin_client, identifier).status_code == 200


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('operation', ['cancel', 'revoke', 'recover'])
def test_postgres_running_worker_stops_before_artifact_publication(admin_client, admin_user, document, monkeypatch, operation):
    postgres_only()
    monkeypatch.setattr('apps.core.events._dispatch_after_commit', lambda: None)
    identifier = submit(admin_client)
    read, resume = Event(), Event()
    original = exporter.guarded_batch
    def pause_after_batch(*args, **kwargs):
        result = original(*args, **kwargs)
        read.set()
        assert resume.wait(15)
        return result
    monkeypatch.setattr(exporter, 'guarded_batch', pause_after_batch)
    monkeypatch.setattr('config.celery.app.control.revoke', lambda *args, **kwargs: None)
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(in_thread, lambda: exporter.run_business_export(identifier))
        try:
            assert read.wait(15), 'worker 未进入真实数据库批次'
            if operation == 'cancel':
                result = admin_client.post('/api/v1/tasks/' + identifier + '/cancel/')
                assert result.status_code == 200, result.content
            elif operation == 'revoke':
                with transaction.atomic():
                    current = type(admin_user).objects.select_for_update().get(pk=admin_user.pk)
                    current.session_version += 1; current.save()
            else:
                TaskRecord.objects.filter(pk=identifier).update(started_at=timezone.now() - timedelta(days=2))
                exporter.recover_lost_exports()
        finally:
            resume.set()
        worker.result(timeout=20)
    record = TaskRecord.objects.get(pk=identifier)
    assert record.status == ('cancelled' if operation == 'cancel' else 'failed'), record.error
    assert not BusinessExportRequest.objects.get(pk=identifier).artifact
