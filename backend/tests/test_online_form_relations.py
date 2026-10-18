"""关联字段协议与表单上下文：登记边界另由真实生成模块验收覆盖。"""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError

from apps.files.models import FileModel
from apps.online_forms import relations
from apps.online_forms.models import OnlineForm, OnlineFormRecord
from apps.online_forms.validators import validate_definition, validate_record
from tests.test_online_forms import grant_record_permissions

pytestmark = pytest.mark.django_db
BASE = '/api/v1/online-forms/relation-form/'


@pytest.fixture(autouse=True)
def registered(settings, monkeypatch):
    settings.ADMINCORE_MODULES = tuple(set(settings.ADMINCORE_MODULES) | {'online_forms', 'files'})
    settings.ROOT_URLCONF = 'tests.online_forms_urls'
    state = {'enabled': True, 'readable': True, 'query': 'contains'}
    service = SimpleNamespace(visible=lambda actor: FileModel.objects.filter(uploader=actor))
    def sources(actor):
        if state['enabled']:
            yield (SimpleNamespace(key='explicit_records'), {'title': '登记资源'}, service, '/records',
                   [{'name': 'original_name', 'query': state['query']}] if state['readable'] else [], 'original_name')
    monkeypatch.setattr(relations, 'sources', sources)
    return state


def definition():
    return validate_definition({'schema_version': 2, 'fields': [
        {'key': 'target', 'label': '业务记录', 'type': 'relation', 'resource': 'explicit_records'},
        {'key': 'lines', 'label': '明细', 'type': 'detail', 'fields': [
            {'key': 'target', 'label': '关联明细', 'type': 'relation', 'resource': 'explicit_records'}]},
    ]})


def form(actor, **extra):
    return OnlineForm.objects.create(code='relation-form', name='关联申请', definition=definition(), status='published', created_by=actor, **extra)


def target(actor, title='授权业务名称'):
    return FileModel.objects.create(uploader=actor, original_name=title, file='relation-unit/unused.txt', file_type='txt', size=1)


def test_approval_submit_rechecks_relation_acl_before_creating_request(admin_client, admin_user, registered, settings):
    from apps.approvals.models import ApprovalRequest
    from tests.test_online_form_approvals import prepare, submit
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'approvals')
    _, _, created = prepare(admin_client, admin_user)
    row = OnlineFormRecord.objects.get(pk=created['id'])
    row.definition_snapshot = validate_definition({'schema_version': 2, 'fields': [
        {'key': 'title', 'label': '标题', 'type': 'text', 'required': True}, definition()['fields'][0]]})
    row.data['target'] = str(target(admin_user).pk)
    row.save()
    registered['readable'] = False
    response = submit(admin_client, created)
    assert response.status_code == 400, response.content
    assert ApprovalRequest.objects.count() == 0
    row.refresh_from_db()
    assert row.version == 1 and row.approval_status == 'draft'


@pytest.mark.parametrize('extra', [{'default': str(uuid4())}, {'resource': 'auth.User'}, {'resource': 'name__secret'},
                                  {'resource': ''}, {'options': ['a']}, {'computation': {'op': 'sum'}}])
def test_relation_schema_rejects_dynamic_paths_defaults_and_calculations(extra):
    with pytest.raises(ValidationError):
        validate_definition({'schema_version': 2, 'fields': [dict(definition()['fields'][0], **extra)]})


@pytest.mark.parametrize('value', ['https://example.com/records/1', 1, [str(uuid4())], {'id': str(uuid4())}])
def test_relation_values_only_accept_uuid(value):
    with pytest.raises(ValidationError):
        validate_record(definition(), {'target': value})


def test_relation_conditions_only_presence_and_resource_forbidden_on_plain_field():
    raw = definition(); raw['fields'].append({'key': 'note', 'label': '备注', 'type': 'text', 'visible_when': [{'field': 'target', 'op': 'eq', 'value': str(uuid4())}]})
    with pytest.raises(ValidationError):
        validate_definition(raw)
    raw['fields'][-1]['visible_when'] = [{'field': 'target', 'op': 'not_empty'}]
    assert validate_definition(raw)['fields'][-1]['visible_when'][0]['op'] == 'not_empty'
    with pytest.raises(ValidationError):
        validate_definition({'schema_version': 2, 'fields': [{'key': 'note', 'label': '备注', 'type': 'text', 'resource': 'explicit_records'}]})


def test_create_update_and_nested_references_reauthorize_without_label_leaks(admin_user, member_user, member_client, registered):
    grant_record_permissions(member_user); source = form(admin_user); own = target(member_user); other = target(admin_user, '不能回显的标题')
    params = {'form_id': source.pk, 'field': 'target', 'selected': other.pk}
    response = member_client.get(BASE + 'relations/', params)
    assert response.status_code == 200 and response['Cache-Control'] == 'private, no-store'
    assert response.json()['data'] == {'items': [{'id': str(own.pk), 'title': own.original_name}], 'selected': None, 'has_more': False}
    assert member_client.post(BASE + 'records/', {'data': {'lines': [{'target': str(other.pk)}]}}, format='json').status_code == 400
    result = member_client.post(BASE + 'records/', {'data': {'target': str(own.pk), 'lines': [{'target': str(own.pk)}]}}, format='json')
    assert result.status_code == 201, result.content
    row = result.json()['data']; registered['readable'] = False
    resolution = member_client.get(BASE + 'relations/', {'record_id': row['id'], 'field': 'target', 'selected': own.pk, 'resolve': 'true'})
    assert resolution.status_code == 400 and own.original_name not in resolution.content.decode()
    assert member_client.patch(BASE + 'records/' + row['id'] + '/', {'version': 1, 'data': row['data']}, format='json').status_code == 400
    saved = OnlineFormRecord.objects.get(pk=row['id']); assert saved.version == 1
    assert member_client.patch(BASE + 'records/' + row['id'] + '/', {'version': 1, 'data': {}}, format='json').status_code == 200


def test_readonly_history_uses_frozen_schema_and_bound_values_only(admin_user, member_user, member_client):
    grant_record_permissions(member_user); source = form(admin_user); own = target(member_user); other = target(member_user)
    response = member_client.post(BASE + 'records/', {'data': {'lines': [{'target': str(own.pk)}]}}, format='json')
    row = response.json()['data']
    source.definition = {'fields': [{'key': 'target', 'label': '普通文本', 'type': 'text'}]}; source.save()
    from apps.permissions.models import RolePermission
    RolePermission.objects.filter(role__userrole__user=member_user, permission__code='online_form:record_update').delete()
    params = {'record_id': row['id'], 'field': 'lines.0.target', 'selected': own.pk, 'resolve': 'true'}
    assert member_client.get(BASE + 'relations/', params).json()['data']['selected']['id'] == str(own.pk)
    assert member_client.get(BASE + 'relations/', {**params, 'selected': other.pk}).json()['data']['selected'] is None
    assert member_client.get(BASE + 'relations/', {**params, 'field': 'target'}).json()['data']['selected'] is None
    assert member_client.get(BASE + 'relations/', {**params, 'resolve': 'false'}).status_code == 403
    assert member_client.get(BASE + 'relations/', {**params, 'record_id': uuid4()}).status_code == 404


def test_form_context_permissions_search_rules_and_strict_parameters(admin_user, member_user, admin_client, member_client, registered):
    grant_record_permissions(member_user); source = form(admin_user); row = target(member_user, 'EXACT-CODE')
    params = {'form_id': source.pk, 'field': 'target'}
    registered['query'] = 'eq'
    assert member_client.get(BASE + 'relations/', {**params, 'q': 'EXACT'}).json()['data']['items'] == []
    assert member_client.get(BASE + 'relations/', {**params, 'q': row.original_name}).json()['data']['items'][0]['id'] == str(row.pk)
    for changes in [{'field': 'target__secret'}, {'tenant_id': uuid4()}, {'model': 'auth.User'}, {'q': ['a', 'b']}, {'record_id': uuid4()}]:
        assert member_client.get(BASE + 'relations/', {**params, **changes}).status_code == 400
    assert member_client.get('/api/v1/online-forms/relation-resources/').status_code == 403
    assert admin_client.get('/api/v1/online-forms/relation-resources/').json()['data'] == [{'code': 'explicit_records', 'title': '登记资源'}]
    source.status = 'draft'; source.save()
    assert member_client.get(BASE + 'relations/', params).status_code == 403
    source.status = 'archived'; source.save()
    assert member_client.get(BASE + 'relations/', params).status_code == 409


def test_publish_and_preview_recheck_registered_resource(admin_client, admin_user, registered):
    source = form(admin_user); source.status = 'draft'; source.save(); row = target(admin_user)
    registered['enabled'] = False
    assert admin_client.post(f'/api/v1/online-forms/forms/{source.pk}/publish/', {'version': 1}, format='json').status_code == 400
    preview = {'form_id': str(source.pk), 'definition': definition(), 'data': {'target': str(row.pk)}}
    assert admin_client.post('/api/v1/online-forms/validate/', preview, format='json').status_code == 400
    registered['enabled'] = True
    assert admin_client.post('/api/v1/online-forms/validate/', preview, format='json').status_code == 200
    assert not OnlineFormRecord.objects.exists()


def test_exact_tenant_context_ignores_foreign_rows_even_for_platform_admin(settings, admin_client, admin_user):
    from apps.core.models import Tenant
    from apps.core.tenancy import tenant_context
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    a, b = Tenant.objects.create(name='甲', slug='form-relation-a'), Tenant.objects.create(name='乙', slug='form-relation-b')
    with tenant_context(a.pk):
        source, own = form(admin_user), target(admin_user)
    with tenant_context(b.pk):
        foreign = target(admin_user, '乙租户机密')
    params = {'form_id': source.pk, 'field': 'target', 'selected': foreign.pk}
    response = admin_client.get(BASE + 'relations/', params)
    assert response.status_code == 200 and response.json()['data']['items'] == [{'id': str(own.pk), 'title': own.original_name}]
    assert response.json()['data']['selected'] is None and foreign.original_name not in response.content.decode()
    assert admin_client.post(BASE + 'records/', {'form_id': source.pk, 'data': {'target': str(foreign.pk)}}, format='json').status_code == 400
    payload = {'form_id': str(source.pk), 'definition': definition(), 'data': {'target': str(own.pk)}}
    assert admin_client.post('/api/v1/online-forms/validate/', payload, format='json').status_code == 200
    assert admin_client.post('/api/v1/online-forms/validate/', payload, format='json', HTTP_X_ADMINCORE_TENANT=str(a.pk)).status_code == 200
    assert admin_client.post('/api/v1/online-forms/validate/', payload, format='json', HTTP_X_ADMINCORE_TENANT=str(b.pk)).status_code == 404
    assert admin_client.get(BASE + 'relations/', params, HTTP_X_ADMINCORE_TENANT=str(b.pk)).status_code == 404


def test_relation_approval_snapshot_excludes_main_and_nested_values(admin_user):
    from apps.approvals.models import ApprovalFlow, ApprovalRequest
    from apps.online_forms.approval_integration import redact_approval_snapshot
    source = form(admin_user); identifier = str(uuid4())
    record = OnlineFormRecord.objects.create(form=source, owner=admin_user, form_version=1,
        definition_snapshot=definition(), data={'target': identifier, 'lines': [{'target': identifier}]})
    flow = ApprovalFlow.objects.create(code='relation-review', name='审批', created_by=admin_user)
    application = ApprovalRequest.objects.create(flow=flow, flow_version=1, applicant=admin_user, assignee=admin_user,
        business_module='online_forms', business_record_id=record.pk, business_snapshot={
            'record_id': str(record.pk), 'definition': deepcopy(definition()), 'data': deepcopy(record.data), 'release_number': 1})
    result = redact_approval_snapshot(application, admin_user, {'extra_data': {'target': identifier}})
    assert identifier not in str(result)
