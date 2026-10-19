"""带审批记录在保存时即满足冻结流程值域，普通表单保持原协议。"""
from copy import deepcopy

import pytest

from apps.approvals.models import ApprovalFlow, ApprovalRequest
from apps.online_forms.models import OnlineFormRecord
from tests.test_online_form_approvals import flow_definition

pytestmark = pytest.mark.django_db
BASE = '/api/v1/online-forms/'
RECORDS = BASE + 'input-contract/records/'


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.ADMINCORE_MODULES = tuple(set(settings.ADMINCORE_MODULES) | {'online_forms', 'approvals'})
    settings.ROOT_URLCONF = 'tests.online_forms_urls'


def publish(client, actor, definition, inputs=None):
    payload = {'name': '输入契约', 'code': 'input-contract', 'definition': definition}
    flow = None
    if inputs is not None:
        graph = flow_definition()
        graph['inputs'] = inputs
        flow = ApprovalFlow.objects.create(code='input-contract-review', name='输入审核',
            status='published', definition=graph, created_by=actor)
        payload['approval_flow_code'] = flow.code
    created = client.post(BASE + 'forms/', payload, format='json')
    assert created.status_code == 201, created.content
    form = created.json()['data']
    response = client.post(f"{BASE}forms/{form['id']}/publish/", {'version': form['version']}, format='json')
    assert response.status_code == 200, response.content
    return flow


@pytest.mark.parametrize('kind,input_kind,bad,good', [
    ('number', 'integer', 1.5, 1),
    ('number', 'integer', 2147483648, 2147483647),
    ('number', 'integer', -2147483649, -2147483648),
    ('text', 'text', 'X' * 201, 'X' * 200),
    ('textarea', 'text', 'X' * 201, 'X' * 200),
    ('text', 'text', 'before\x00after', '正常文本'),
    ('text', 'text', None, '补齐输入'),
    ('boolean', 'boolean', None, False),
])
def test_invalid_input_rejected_before_save_and_valid_value_can_submit(admin_client, admin_user, kind, input_kind, bad, good):
    # 保留默认文本长度和可选字段；只约束实际流入审批的记录值。
    publish(admin_client, admin_user, {'fields': [{'key': 'value', 'label': '值', 'type': kind}]},
            [{'key': 'value', 'type': input_kind}])
    invalid = {} if bad is None else {'value': bad}
    rejected = admin_client.post(RECORDS, {'data': invalid}, format='json')
    assert rejected.status_code == 400, rejected.content
    assert 'value' in rejected.json()['data']
    assert not OnlineFormRecord.objects.exists() and not ApprovalRequest.objects.exists()
    created = admin_client.post(RECORDS, {'data': {'value': good}}, format='json')
    assert created.status_code == 201, created.content
    row = created.json()['data']
    rejected = admin_client.patch(RECORDS + row['id'] + '/', {'version': 1, 'data': invalid}, format='json')
    assert rejected.status_code == 400 and 'value' in rejected.json()['data'], rejected.content
    saved = OnlineFormRecord.objects.get(pk=row['id'])
    assert saved.version == 1 and saved.data == {'value': good}
    response = admin_client.post(RECORDS + row['id'] + '/submit-approval/', {'version': 1}, format='json')
    assert response.status_code == 200, response.content
    application = ApprovalRequest.objects.get(pk=response.json()['data']['approval_request'])
    assert application.extra_data == {'value': good}


def test_unbound_form_retains_fractional_large_numeric_and_long_text_values(admin_client, admin_user):
    fields = [{'key': key, 'label': key, 'type': kind} for key, kind in
              [('fraction', 'number'), ('large', 'number'), ('text', 'text'), ('optional', 'text')]]
    publish(admin_client, admin_user, {'fields': fields})
    values = {'fraction': 1.5, 'large': 2147483648, 'text': 'X' * 201}
    response = admin_client.post(RECORDS, {'data': values}, format='json')
    assert response.status_code == 201 and response.json()['data']['data'] == values, response.content


def test_computed_input_and_history_use_frozen_flow_during_save_and_submission(admin_client, admin_user):
    definition = {'schema_version': 2, 'fields': [
        {'key': key, 'label': key, 'type': 'decimal', 'scale': 2} for key in ['price', 'quantity']
    ] + [{'key': 'total', 'label': '合计', 'type': 'decimal', 'scale': 2, 'required': True,
          'computation': {'op': 'multiply', 'operands': [{'field': 'price'}, {'field': 'quantity'}]}}]}
    flow = publish(admin_client, admin_user, definition, [{'key': 'total', 'type': 'decimal'}])
    created = admin_client.post(RECORDS, {'data': {'price': '1.50', 'quantity': '2', 'total': '999'}}, format='json')
    assert created.status_code == 201, created.content
    row = created.json()['data']
    assert row['data']['total'] == '3.00'
    # 同编码的新流程采用完全不同输入，不影响旧记录所属发布版。
    flow.status = 'archived'
    flow.save(update_fields=['status'])
    newer = deepcopy(flow.definition)
    newer['inputs'] = [{'key': 'other', 'type': 'text'}]
    ApprovalFlow.objects.create(code=flow.code, name='新版审核', revision=2,
        status='published', definition=newer, created_by=admin_user)
    saved = admin_client.patch(RECORDS + row['id'] + '/', {'version': 1,
        'data': {'price': '2.50', 'quantity': '2', 'total': '伪造值'}}, format='json')
    assert saved.status_code == 200 and saved.json()['data']['data']['total'] == '5.00', saved.content
    result = admin_client.post(RECORDS + row['id'] + '/submit-approval/', {'version': 2}, format='json')
    assert result.status_code == 200, result.content
    application = ApprovalRequest.objects.get(pk=result.json()['data']['approval_request'])
    assert application.flow_id == flow.pk and application.extra_data == {'total': '5.00'}


def test_conditionally_hidden_input_cannot_save_unsendable_record(admin_client, admin_user):
    publish(admin_client, admin_user, {'schema_version': 2, 'fields': [
        {'key': 'show', 'label': '显示', 'type': 'boolean'},
        {'key': 'value', 'label': '条件值', 'type': 'text',
         'visible_when': [{'field': 'show', 'op': 'eq', 'value': True}]},
    ]}, [{'key': 'value', 'type': 'text'}])
    response = admin_client.post(RECORDS, {'data': {'show': False, 'value': '隐藏旧值'}}, format='json')
    assert response.status_code == 400 and 'value' in response.json()['data'], response.content
    assert not OnlineFormRecord.objects.exists()
    response = admin_client.post(RECORDS, {'data': {'show': True, 'value': '现在可见'}}, format='json')
    assert response.status_code == 201, response.content
    row = response.json()['data']
    submitted = admin_client.post(RECORDS + row['id'] + '/submit-approval/', {'version': row['version']}, format='json')
    assert submitted.status_code == 200, submitted.content
