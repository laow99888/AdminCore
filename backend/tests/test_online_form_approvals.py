"""在线表单审批：真实路由闭环、冻结流程、权限与附件投影。"""
from copy import deepcopy
import json

import pytest
from django.db.models.deletion import ProtectedError

from apps.approvals.models import ApprovalFlow, ApprovalRequest
from apps.online_forms.approval_integration import redact_approval_snapshot
from apps.online_forms.models import OnlineForm, OnlineFormRecord
from tests.test_online_forms import grant_record_permissions

pytestmark = pytest.mark.django_db
BASE = '/api/v1/online-forms/approval-form/records/'


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.ADMINCORE_MODULES = tuple(set(settings.ADMINCORE_MODULES) | {'online_forms', 'approvals', 'files'})
    settings.ROOT_URLCONF = 'tests.online_forms_urls'


def flow_definition():
    return {'schema_version': 2, 'inputs': [{'key': 'title', 'type': 'text'}],
            'nodes': [{'id': 'start', 'type': 'start'},
                      {'id': 'review', 'type': 'user', 'assignee': {'source': 'applicant'}},
                      {'id': 'end', 'type': 'end'}],
            'edges': [{'from': 'start', 'to': 'review'}, {'from': 'review', 'to': 'end'}]}


def prepare(client, actor, **extra):
    flow = ApprovalFlow.objects.create(code='online-record-review', name='记录审核', status='published',
                                      definition=flow_definition(), created_by=actor, **extra)
    response = client.post('/api/v1/online-forms/forms/', {'name': '记录申请', 'code': 'approval-form',
        'approval_flow_code': flow.code, 'definition': {'fields': [{'key': 'title', 'label': '标题', 'type': 'text', 'required': True}]}}, format='json')
    assert response.status_code == 201, response.content
    form = response.json()['data']
    response = client.post(f"/api/v1/online-forms/forms/{form['id']}/publish/", {'version': form['version']}, format='json')
    assert response.status_code == 200, response.content
    assert response.json()['data']['approval_flow'] == str(flow.pk)
    record = client.post(BASE, {'data': {'title': '原始机密'}}, format='json')
    assert record.status_code == 201, record.content
    return flow, OnlineForm.objects.get(pk=form['id']), record.json()['data']


def submit(client, record, **extra):
    return client.post(BASE + record['id'] + '/submit-approval/', {'version': record['version'], **extra}, format='json')


@pytest.mark.parametrize('decision,status', [('approve', 'approved'), ('reject', 'rejected')])
def test_terminal_decision_writes_back_and_reject_allows_edit(admin_client, admin_user, decision, status):
    flow, form, record = prepare(admin_client, admin_user)
    response = submit(admin_client, record, business_snapshot={'data': {'title': '伪造'}}, extra_data={'title': '伪造'})
    assert response.status_code == 200, response.content
    row = response.json()['data']
    assert row['approval_status'] == 'pending' and row['version'] == 2 and row['approval_enabled'] is True
    application = ApprovalRequest.objects.get(pk=row['approval_request'])
    assert application.extra_data == {'title': '原始机密'} and application.flow_id == flow.pk
    assert application.business_snapshot['data']['title'] == '原始机密'
    assert admin_client.patch(BASE + row['id'] + '/', {'version': 2, 'data': {'title': '修改'}}, format='json').status_code == 409
    assert submit(admin_client, row).status_code == 409
    result = admin_client.post(f'/api/v1/approvals/{application.pk}/{decision}/', {
        'comment': '处理', 'expected_workflow_version': application.workflow_version,
        'step_id': str(application.steps.get(status='pending').pk)}, format='json')
    assert result.status_code == 200, result.content
    detail = admin_client.get(BASE + row['id'] + '/').json()['data']
    assert detail['approval_status'] == status and detail['version'] == 3
    updated = admin_client.patch(BASE + row['id'] + '/', {'version': 3, 'data': {'title': '驳回修改'}}, format='json')
    assert updated.status_code == (409 if status == 'approved' else 200), updated.content
    if status == 'rejected':
        again = submit(admin_client, updated.json()['data'])
        assert again.status_code == 200 and again.json()['data']['approval_request'] != str(application.pk)
        application.refresh_from_db()
        assert application.business_snapshot['data']['title'] == '原始机密'


def test_withdraw_uses_version_and_retains_approval_history(admin_client, admin_user):
    _, _, record = prepare(admin_client, admin_user)
    row = submit(admin_client, record).json()['data']
    path = BASE + row['id'] + '/withdraw-approval/'
    assert admin_client.post(path, {'version': 1}, format='json').status_code == 409
    response = admin_client.post(path, {'version': 2}, format='json')
    assert response.status_code == 200, response.content
    assert response.json()['data']['approval_status'] == 'cancelled'
    application = ApprovalRequest.objects.get(pk=row['approval_request'])
    assert application.status == 'cancelled' and not application.steps.filter(status='pending').exists()
    with pytest.raises(ProtectedError):
        application.delete()
    assert admin_client.post(path, {'version': 3}, format='json').status_code == 409


def test_flow_new_revision_never_changes_old_form_routing(admin_client, admin_user):
    flow, form, record = prepare(admin_client, admin_user)
    flow.status = 'archived'; flow.save()
    new = ApprovalFlow.objects.create(code=flow.code, revision=2, name='新版流程', status='published',
        version=8, definition=flow_definition(), created_by=admin_user)
    response = submit(admin_client, record)
    assert response.status_code == 200, response.content
    application = ApprovalRequest.objects.get(pk=response.json()['data']['approval_request'])
    assert application.flow_id == flow.pk and application.flow_version == form.approval_flow_version
    assert application.flow_id != new.pk
    with pytest.raises(ProtectedError):
        flow.delete()


@pytest.mark.parametrize('version', [None, True, 0, '1'])
def test_requires_strict_record_version(admin_client, admin_user, version):
    _, _, record = prepare(admin_client, admin_user)
    response = admin_client.post(BASE + record['id'] + '/submit-approval/', {'version': version}, format='json')
    assert response.status_code == 400
    assert ApprovalRequest.objects.count() == 0


def test_submit_permission_and_ownership_checked(admin_client, admin_user, member_client, member_user):
    _, form, record = prepare(admin_client, admin_user)
    grant_record_permissions(member_user)
    own = OnlineFormRecord.objects.create(form=form, form_version=1, owner=member_user, data={'title': '本人'})
    assert submit(member_client, {'id': str(own.pk), 'version': 1}).status_code == 403
    from apps.permissions.models import Permission, RolePermission
    permission = Permission.objects.get(code='online_form:record_submit')
    RolePermission.objects.create(role=member_user.roles.first().role, permission=permission)
    assert submit(member_client, record).status_code == 404
    assert submit(member_client, {'id': str(own.pk), 'version': 1}).status_code == 200


@pytest.mark.parametrize('kind', ['file', 'detail', 'datetime', 'multiselect', 'number'])
def test_publish_rejects_mismatched_top_level_inputs(admin_client, admin_user, kind):
    ApprovalFlow.objects.create(code='online-record-review', name='审核', status='published', definition=flow_definition(), created_by=admin_user)
    field = {'key': 'title', 'label': '标题', 'type': kind}
    if kind == 'detail':
        field['fields'] = [{'key': 'title', 'label': '内层', 'type': 'text'}]
    if kind == 'multiselect':
        field['options'] = ['A']
    created = admin_client.post('/api/v1/online-forms/forms/', {'name': '不匹配', 'code': 'approval-form',
        'approval_flow_code': 'online-record-review', 'definition': {'schema_version': 2, 'fields': [field]}}, format='json')
    assert created.status_code == 201, created.content
    response = admin_client.post(f"/api/v1/online-forms/forms/{created.json()['data']['id']}/publish/", format='json')
    assert response.status_code == 400, response.content


def test_cross_tenant_flow_not_resolved_by_unselected_platform_admin(admin_client, admin_user):
    from apps.core.models import Tenant
    tenant = Tenant.objects.create(name='其他租户', slug='other-online-approval')
    ApprovalFlow.objects.create(code='online-record-review', name='审核', status='published', definition=flow_definition(),
                                tenant=tenant, created_by=admin_user)
    created = admin_client.post('/api/v1/online-forms/forms/', {'name': '无租户表单', 'code': 'approval-form',
        'approval_flow_code': 'online-record-review', 'definition': {'fields': [{'key': 'title', 'label': '标题', 'type': 'text'}]}}, format='json')
    response = admin_client.post(f"/api/v1/online-forms/forms/{created.json()['data']['id']}/publish/", format='json')
    assert response.status_code == 400


def test_projection_hides_nested_files_and_revoked_reader(admin_user, member_user):
    from tests.test_online_form_attachments import definition, document
    grant_record_permissions(member_user)
    file = document(admin_user)
    frozen = {'release_number': 1, 'definition': definition(), 'data': {
        'title': '可见文本', 'proof': str(file.pk), 'lines': [{'proof': str(file.pk)}]}}
    application = ApprovalRequest(business_module='online_forms', business_snapshot=frozen)
    serialized = {'title': '包含机密的旧标题', 'extra_data': {'secret': '机密'}, 'business_snapshot': frozen}
    result = redact_approval_snapshot(application, member_user, serialized)
    encoded = json.dumps(result, ensure_ascii=False)
    assert str(file.pk) not in encoded and file.original_name not in encoded and '机密' not in encoded
    assert result['business_snapshot']['fields']['标题 (title)'] == '可见文本'
    member_user.roles.all().delete()
    assert redact_approval_snapshot(application, member_user, serialized)['business_snapshot'] == {}
    # 即使历史快照被外部破坏，也不能把未知嵌套 JSON 直接发送给客户端。
    bad = deepcopy(frozen); bad['definition']['fields'][0]['html'] = '<b>敏感</b>'
    application.business_snapshot = bad
    assert redact_approval_snapshot(application, admin_user, serialized)['business_snapshot'] == {}


def test_attachment_submit_rechecks_acl_and_protects_history(admin_client, admin_user):
    from tests.test_online_form_attachments import definition, document
    from apps.approvals.models import ApprovalFileReference
    flow, form, record = prepare(admin_client, admin_user)
    form.definition = definition(); form.save()
    file = document(admin_user)
    row = OnlineFormRecord.objects.get(pk=record['id'])
    row.definition_snapshot = definition()
    row.data = {'title': '审批附件', 'proof': str(file.pk), 'lines': [{'proof': str(file.pk)}]}
    row.save()
    result = submit(admin_client, record)
    assert result.status_code == 200, result.content
    application = ApprovalRequest.objects.get(pk=result.json()['data']['approval_request'])
    assert ApprovalFileReference.objects.filter(request=application, file=file).count() == 1
    detail = admin_client.get(f'/api/v1/approvals/{application.pk}/')
    assert detail.status_code == 200, detail.content
    assert str(file.pk) not in json.dumps(detail.json())
    assert admin_client.post(BASE + record['id'] + '/withdraw-approval/', {'version': 2}, format='json').status_code == 200
    from apps.core.models import LifecycleConflict
    with pytest.raises(LifecycleConflict):
        file.hard_delete()
    file.is_deleted = True; file.save()
    assert submit(admin_client, {**record, 'version': 3}).status_code == 400
    assert ApprovalRequest.objects.count() == 1


def test_flow_choices_use_form_tenant_and_require_admin(settings, admin_client, admin_user, member_client):
    from apps.core.models import Tenant
    from apps.core.tenancy import tenant_context
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    first = Tenant.objects.create(slug='approval-choices-a', name='A')
    second = Tenant.objects.create(slug='approval-choices-b', name='B')
    with tenant_context(first.pk):
        flow = ApprovalFlow.objects.create(code='choices-first', name='A审核', status='published', definition=flow_definition(), created_by=admin_user)
        form = OnlineForm.objects.create(code='choices-form', name='A表单', created_by=admin_user, definition={'fields': []})
    with tenant_context(second.pk):
        ApprovalFlow.objects.create(code='choices-second', name='B审核', status='published', definition=flow_definition(), created_by=admin_user)
    url = '/api/v1/online-forms/approval-flows/'
    assert admin_client.get(url).json()['data'] == []
    result = admin_client.get(url, {'form_id': str(form.pk)})
    assert [item['code'] for item in result.json()['data']] == [flow.code]
    assert 'definition' not in result.json()['data'][0]
    assert admin_client.get(url, {'form_id': str(form.pk)}, HTTP_X_ADMINCORE_TENANT=str(second.pk)).status_code == 404
    assert member_client.get(url).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_postgres_withdraw_and_final_decision_serialize(admin_client, admin_user, member_user):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import connection, connections
    from rest_framework.test import APIClient
    if connection.vendor != 'postgresql':
        pytest.skip('需要真实 PostgreSQL 申请和记录行锁')
    from apps.permissions.models import Permission, RolePermission
    grant_record_permissions(member_user)
    role = member_user.roles.first().role
    for code in ['online_form:record_submit', 'online_form:record_withdraw']:
        RolePermission.objects.create(role=role, permission=Permission.objects.get(code=code))
    flow, form, _ = prepare(admin_client, admin_user)
    definition = flow_definition()
    definition['nodes'][1] = {'id': 'review', 'type': 'user', 'assignee_ids': [str(admin_user.pk)]}
    # 测试夹具直接设置发布内容；正常 API 禁止修改已发布版本。
    ApprovalFlow.objects.filter(pk=flow.pk).update(definition=definition)
    record = OnlineFormRecord.objects.create(form=form, owner=member_user, form_version=1, data={'title': '并发审批'})
    member = APIClient(); member.force_authenticate(member_user)
    result = submit(member, {'id': str(record.pk), 'version': 1})
    assert result.status_code == 200, result.content
    application = ApprovalRequest.objects.get(pk=result.json()['data']['approval_request'])
    gate = Barrier(2)
    # 在启动线程前冻结步骤 ID，撤回先获锁时不能以测试夹具的查询失败代替并发结果。
    step_id = str(application.steps.get(status='pending').pk)
    def approve_or_withdraw(operation):
        try:
            actor = admin_user if operation == 'approve' else member_user
            client = APIClient(); client.force_authenticate(actor)
            gate.wait(timeout=10)
            url = f'/api/v1/approvals/{application.pk}/approve/' if operation == 'approve' else BASE + str(record.pk) + '/withdraw-approval/'
            payload = {'comment': '', 'expected_workflow_version': application.workflow_version, 'step_id': step_id} if operation == 'approve' else {'version': 2}
            response = client.post(url, payload, format='json')
            return response.status_code, response.content
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(approve_or_withdraw, operation) for operation in ['approve', 'withdraw']]
        results = [future.result(timeout=20) for future in futures]
    assert sorted(status for status, _ in results) in [[200, 400], [200, 409]], results
    application.refresh_from_db(); record.refresh_from_db()
    assert application.status == record.approval_status and record.approval_status in {'approved', 'cancelled'}
    assert record.version == 3 and not application.steps.filter(status='pending').exists()
