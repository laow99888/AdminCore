"""条件流程契约和真实审批中心回归。"""
from copy import deepcopy
from uuid import uuid4
import pytest
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.approvals.graph import next_node, validate_inputs
from apps.approvals.models import ApprovalFlow, ApprovalRequest, validate_flow_definition
from apps.permissions.models import Role, UserRole


def definition(role_id=None):
    return {'schema_version': 2, 'inputs': [{'key': 'amount', 'type': 'decimal'}],
        'nodes': [{'id': 'start', 'type': 'start'}, {'id': 'gate', 'type': 'branch'},
                  {'id': 'large', 'type': 'user', 'assignee': {'source': 'role', 'role_id': str(role_id or uuid4())}},
                  {'id': 'small', 'type': 'user', 'assignee': {'source': 'applicant'}},
                  {'id': 'end', 'type': 'end'}],
        'edges': [{'from': 'start', 'to': 'gate'},
                  {'from': 'gate', 'to': 'large', 'when': {'field': 'amount', 'op': 'gte', 'value': '1000.00'}},
                  {'from': 'gate', 'to': 'small', 'default': True},
                  {'from': 'large', 'to': 'end'}, {'from': 'small', 'to': 'end'}]}


@pytest.mark.parametrize('amount,expected', [('999.99', 'small'), ('1000.00', 'large'), ('90071992547409.91', 'large'), ('-0.00', 'small')])
def test_decimal_branch_is_exact(amount, expected):
    design = definition(); validate_flow_definition(design)
    assert next_node(design, 'gate', {'amount': amount}) == expected


@pytest.mark.parametrize('mutate', [
    lambda d: d['edges'].pop(2),
    lambda d: d['edges'][2].update(default=False),
    lambda d: d['edges'].append({'from': 'gate', 'to': 'small', 'default': True}),
    lambda d: d['edges'][1]['when'].update(field='private'),
    lambda d: d['edges'][1]['when'].update(value=1000.0),
    lambda d: d['edges'][1]['when'].update(op='eval'),
    lambda d: d['edges'][3].update(to='gate'),
    lambda d: d['edges'][2].update(to='end'),
    lambda d: d['nodes'][2].update(assignee_ids=[str(uuid4())]),
    lambda d: d['inputs'].append({'key': 'amount', 'type': 'integer'}),
    lambda d: d['nodes'][1].update(type='parallel'),
    lambda d: d.update(schema_version=True),
    lambda d: d['edges'][0].update(when={'field': 'amount', 'op': 'eq', 'value': '1'}),
])
def test_unsafe_graphs_rejected(mutate):
    design = deepcopy(definition()); mutate(design)
    with pytest.raises(ValidationError):
        validate_flow_definition(design)


@pytest.mark.parametrize('value', [None, {}, {'amount': 1.0}, {'amount': '1e2'}, {'amount': 'NaN'}, {'amount': '1', 'private': 'spoof'}])
def test_invalid_snapshot_inputs_rejected(value):
    with pytest.raises(ValidationError):
        validate_inputs(definition(), value)


@pytest.mark.django_db
def test_selected_path_only_and_dynamic_role_rechecked(admin_client, admin_user, member_user):
    role = Role.objects.create(name='采购审核')
    UserRole.objects.create(role=role, user=member_user)
    flow = ApprovalFlow.objects.create(name='条件采购', code='graph-v2', status='published',
        definition=definition(role.pk), created_by=admin_user)
    def submit(amount, **extra):
        return admin_client.post('/api/v1/approvals/', {'title': '采购', 'content': '正文',
            'flow_id': str(flow.pk), 'extra_data': {'amount': amount}, **extra}, format='json')
    small = submit('0.10'); assert small.status_code == 201, small.content
    assert small.json()['data']['current_node'] == 'small'
    assert len(small.json()['data']['steps']) == 1
    large = submit('1000.00'); assert large.status_code == 201, large.content
    row = large.json()['data']; assert row['assignee'] == str(member_user.pk) and row['current_node'] == 'large'
    assert admin_client.post(f"/api/v1/approvals/{row['id']}/approve/", format='json').status_code == 403
    client = APIClient(); client.force_authenticate(member_user)
    assert client.post(f"/api/v1/approvals/{row['id']}/approve/", format='json').json()['data']['status'] == 'approved'
    role.is_active = False; role.save(update_fields=['is_active'])
    before = ApprovalRequest.objects.count()
    assert submit('2000.00').status_code == 400
    assert ApprovalRequest.objects.count() == before
    assert submit('0.01').status_code == 201  # 未选分支的空角色不影响当前路径。
    assert submit('1.00', extra_data={'amount': '1.00', 'business_module': 'spoof'}).status_code == 400


@pytest.mark.django_db
def test_dynamic_next_role_resolves_on_entry_and_failure_rolls_back(admin_client, admin_user, member_user):
    role = Role.objects.create(name='下一层角色')
    design = definition(role.pk)
    design['edges'][2]['to'] = 'small'
    design['edges'][4]['to'] = 'large'
    flow = ApprovalFlow.objects.create(name='多级', code='late-role', status='published', definition=design, created_by=admin_user)
    response = admin_client.post('/api/v1/approvals/', {'title': '低额', 'content': '正文', 'flow_id': str(flow.pk), 'extra_data': {'amount': '1'}}, format='json')
    row = response.json()['data']; url = f"/api/v1/approvals/{row['id']}/approve/"
    assert admin_client.post(url, format='json').status_code == 409
    request = ApprovalRequest.objects.get(pk=row['id'])
    assert request.current_node == 'small' and request.steps.get().status == 'pending'
    UserRole.objects.create(role=role, user=member_user)
    moved = admin_client.post(url, format='json')
    assert moved.status_code == 200 and moved.json()['data']['current_node'] == 'large'


def test_legacy_fan_out_is_still_rejected():
    from tests.test_advanced_approvals import definition as legacy
    user = type('Person', (), {'id': uuid4()})()
    design = legacy(user); design['edges'].append({'from': 'start', 'to': 'end'})
    with pytest.raises(ValidationError): validate_flow_definition(design)


@pytest.mark.django_db
def test_dynamic_role_and_fixed_assignees_stay_in_tenant(admin_user, member_user, settings):
    from apps.approvals.graph import resolve_assignees
    from apps.core.models import Tenant, TenantMembership
    from apps.core.tenancy import tenant_context
    from rest_framework.exceptions import ValidationError as APIValidationError
    a = Tenant.objects.create(slug='graph-a', name='A'); b = Tenant.objects.create(slug='graph-b', name='B')
    role = Role.objects.create(name='B审批角色', tenant=b)
    UserRole.objects.create(role=role, user=member_user, tenant=b)
    TenantMembership.objects.create(tenant=a, user=admin_user)
    TenantMembership.objects.create(tenant=b, user=member_user)
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    application = ApprovalRequest(applicant=admin_user, tenant=a)
    with tenant_context(a.pk):
        assert resolve_assignees(application, {'assignee': {'source': 'applicant'}})[0].pk == admin_user.pk
        with pytest.raises(APIValidationError):
            resolve_assignees(application, {'assignee': {'source': 'role', 'role_id': str(role.pk)}})
        with pytest.raises(APIValidationError):
            resolve_assignees(application, {'assignee_ids': [str(member_user.pk)]})
