"""任期、主管节点与授权兼容的公开接口验收。"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.approvals.graph import resolve_assignment
from apps.approvals.models import ApprovalFlow, ApprovalRequest, validate_flow_definition
from apps.core.appointments import department_leader
from apps.core.models import Department, OrganizationAppointment, OrganizationMembership, Tenant, TenantMembership
from apps.core.tenancy import tenant_context

pytestmark = pytest.mark.django_db
BASE = '/api/v1/organization/appointments/'


def flow_definition(levels=1):
    return {'schema_version': 2, 'inputs': [], 'nodes': [
        {'id': 'start', 'type': 'start'},
        {'id': 'review', 'type': 'user', 'assignee': {'source': 'department_leader', 'levels': levels}},
        {'id': 'end', 'type': 'end'}], 'edges': [{'from': 'start', 'to': 'review'}, {'from': 'review', 'to': 'end'}]}


def payload(user, department, **extra):
    return {'user': str(user.pk), 'department': str(department.pk), 'kind': 'primary',
            'starts_on': timezone.localdate().isoformat(), 'reason': '入职任命', 'version': 0, **extra}


def test_appointment_crud_overlap_handover_history_and_end(admin_client, member_user):
    day = timezone.localdate()
    department = Department.objects.create(name='采购')
    other = Department.objects.create(name='财务')
    response = admin_client.post(BASE, payload(member_user, department), format='json')
    assert response.status_code == 201, response.data
    row = response.json()['data']; url = BASE + row['id'] + '/'
    for target in (department, other):
        assert admin_client.post(BASE, payload(member_user, target), format='json').status_code == 400
    assert admin_client.post(BASE, payload(member_user, department, kind='secondary'), format='json').status_code == 400
    assert admin_client.post(BASE, payload(member_user, other, kind='secondary'), format='json').status_code == 201
    for method in ('patch', 'put', 'delete'):
        assert getattr(admin_client, method)(url, {}, format='json').status_code == 405
    body = {'ends_on': (day + timedelta(days=2)).isoformat(), 'reason': '调岗交接', 'version': 1}
    assert admin_client.post(url + 'end/', {**body, 'version': 0}, format='json').status_code == 400
    assert admin_client.post(url + 'end/', {**body, 'version': 2}, format='json').status_code == 409
    ended = admin_client.post(url + 'end/', body, format='json')
    assert ended.status_code == 200 and ended.json()['data']['version'] == 2
    assert admin_client.post(url + 'end/', {**body, 'version': 2}, format='json').status_code == 400
    assert admin_client.post(BASE, payload(member_user, department, starts_on=body['ends_on']), format='json').status_code == 201
    active = admin_client.get(BASE, {'as_of': body['ends_on'], 'kind': 'primary'}).json()['data']['items']
    assert len(active) == 1 and active[0]['id'] != row['id']
    assert admin_client.get(BASE).json()['data']['pagination']['total'] == 3
    assert admin_client.delete(f'/api/v1/organization/departments/{department.pk}/').status_code == 400


def test_future_cancel_and_cancelled_primary_never_resurrects_legacy(admin_client, member_user, admin_user):
    day = timezone.localdate(); department = Department.objects.create(name='采购', leader=admin_user)
    OrganizationMembership.objects.create(user=member_user, department=department)
    future = admin_client.post(BASE, payload(member_user, department, starts_on=(day + timedelta(days=1)).isoformat()), format='json').json()['data']
    url = BASE + future['id'] + '/cancel/'
    assert admin_client.post(url, {'version': 1, 'reason': '撤销计划'}, format='json').status_code == 200
    assert admin_client.post(url, {'version': 1, 'reason': '重试'}, format='json').status_code == 409
    app = ApprovalRequest(applicant=member_user)
    with pytest.raises(ValidationError, match='有效主职'):
        department_leader(app, 1)
    assert admin_client.get(BASE, {'as_of': day.isoformat()}).json()['data']['items'] == []
    current = admin_client.post(BASE, payload(member_user, department), format='json').json()['data']
    assert admin_client.post(BASE + current['id'] + '/cancel/', {'version': 1, 'reason': '不允许删除历史'}, format='json').status_code == 400


@pytest.mark.parametrize('changes', [
    {'kind': 'manager'}, {'starts_on': 'wrong'}, {'ends_on': '1900-01-01'}, {'reason': ''},
    {'version': 1}, {'cancelled': True}, {'tenant': 'spoof'}, {'reason': 'x' * 501},
])
def test_invalid_appointment_rejected_without_writes(admin_client, member_user, changes):
    department = Department.objects.create(name='D')
    assert admin_client.post(BASE, payload(member_user, department, **changes), format='json').status_code == 400
    assert not OrganizationAppointment.objects.exists()


@pytest.mark.parametrize('changes,expected', [({'is_active': False}, 401), ({'is_staff': False, 'is_superuser': False}, 403), ({'must_change_password': True}, 403)])
def test_stale_actor_cannot_create_appointment(admin_user, member_user, changes, expected):
    department = Department.objects.create(name='D'); client = APIClient(); client.force_authenticate(admin_user)
    get_user_model().objects.filter(pk=admin_user.pk).update(**changes)
    assert client.post(BASE, payload(member_user, department), format='json').status_code == expected
    assert not OrganizationAppointment.objects.exists()


def test_admin_only_and_people_revalidated_under_lock(admin_client, member_client, member_user):
    department = Department.objects.create(name='D')
    assert member_client.get(BASE).status_code == 403
    assert member_client.post(BASE, payload(member_user, department), format='json').status_code == 403
    from apps.auth_app.write_authorization import authorize_write
    def deactivate(request, *args, **kwargs):
        result = authorize_write(request, *args, **kwargs)
        get_user_model().objects.filter(pk=member_user.pk).update(is_active=False)
        return result
    with patch('apps.core.appointment_views.authorize_write', side_effect=deactivate):
        assert admin_client.post(BASE, payload(member_user, department), format='json').status_code == 400
    assert not OrganizationAppointment.objects.exists()


@pytest.mark.parametrize('levels', [0, 11, True, '1', None, {}, []])
def test_supervisor_definition_rejects_invalid_levels(levels):
    with pytest.raises(ModelValidationError):
        validate_flow_definition(flow_definition(levels))


def test_supervisor_definition_rejects_unregistered_properties():
    value = flow_definition(); value['nodes'][1]['assignee']['skip_missing'] = True
    with pytest.raises(ModelValidationError): validate_flow_definition(value)


def test_appointment_schema_matches_enveloped_detail_and_create():
    from django.urls import include, path
    from drf_spectacular.generators import SchemaGenerator
    schema = SchemaGenerator(patterns=[path('organization/', include('apps.core.organization_urls'))]).get_schema(public=True)
    for route, method, status in [('/organization/appointments/', 'post', '201'), ('/organization/appointments/{id}/', 'get', '200')]:
        reference = schema['paths'][route][method]['responses'][status]['content']['application/json']['schema']['$ref']
        definition = schema['components']['schemas'][reference.rsplit('/', 1)[-1]]
        assert set(definition['required']) == {'code', 'message', 'data'}
        assert definition['properties']['data']['$ref'].endswith('/Appointment')


def test_legacy_fallback_and_secondary_does_not_expand_authorization(admin_user, member_user):
    from apps.core.data_scope import scope_queryset
    from apps.core.models import DataScopeGrant
    from apps.permissions.models import Role, UserRole
    one = Department.objects.create(name='原部门', leader=admin_user); two = Department.objects.create(name='兼职部门')
    OrganizationMembership.objects.create(user=member_user, department=one)
    OrganizationAppointment.objects.create(user=member_user, department=two, kind='secondary', starts_on=timezone.localdate(), reason='兼任')
    users, context = resolve_assignment(ApprovalRequest(applicant=member_user), flow_definition()['nodes'][1])
    assert users == [admin_user] and context['appointment_id'] is None
    outside = get_user_model().objects.create_user('outside')
    OrganizationMembership.objects.create(user=outside, department=two)
    role = Role.objects.create(name='scope'); UserRole.objects.create(user=member_user, role=role)
    DataScopeGrant.objects.create(role=role, resource='user', scope='department')
    assert list(scope_queryset(get_user_model().objects.all(), member_user, 'user', 'pk')) == [member_user]


def test_effective_primary_chain_and_frozen_pending_step(admin_client, admin_user, member_user):
    parent = Department.objects.create(name='总部', leader=admin_user)
    child = Department.objects.create(name='采购', parent=parent, leader=admin_user)
    day = timezone.localdate()
    record = OrganizationAppointment.objects.create(user=member_user, department=child, kind='primary', starts_on=day, reason='入职')
    flow = ApprovalFlow.objects.create(name='主管审批', code='leader', status='published', definition=flow_definition(2), created_by=admin_user)
    app = ApprovalRequest(applicant=member_user)
    leader, context = department_leader(app, 2)
    assert leader == admin_user and context['department_id'] == str(parent.pk) and context['appointment_id'] == str(record.pk)
    client = APIClient(); client.force_authenticate(member_user)
    response = client.post('/api/v1/approvals/', {'title': '入职采购', 'content': '正文', 'flow_id': str(flow.pk)}, format='json')
    assert response.status_code == 201, response.data
    data = response.json()['data']; step = data['steps'][0]
    assert step['assignment_context']['department_name'] == '总部'
    parent.name = '总部新名称'; parent.leader = member_user; parent.save()
    detail = admin_client.get('/api/v1/approvals/' + data['id'] + '/').json()
    assert detail['steps'][0]['assignee'] == str(admin_user.pk)
    assert detail['steps'][0]['assignment_context']['department_name'] == '总部'
    with pytest.raises(ValidationError, match='申请人'):
        department_leader(app, 2)
    assert admin_client.post('/api/v1/approvals/' + data['id'] + '/approve/', {}, format='json').status_code == 200


@pytest.mark.parametrize('change', ['expired', 'future', 'cancelled', 'missing', 'inactive_department', 'inactive_leader', 'self', 'cycle', 'duplicate'])
def test_unavailable_supervisor_fails_closed(admin_user, member_user, change):
    day = timezone.localdate(); department = Department.objects.create(name='D', leader=admin_user)
    OrganizationMembership.objects.create(user=member_user, department=department)
    record = OrganizationAppointment.objects.create(user=member_user, department=department, kind='primary', starts_on=day - timedelta(days=2), reason='任命')
    if change == 'expired': record.ends_on = day
    elif change == 'future': record.starts_on = day + timedelta(days=1)
    elif change == 'cancelled': record.cancelled = True
    elif change == 'missing': department.leader = None
    elif change == 'inactive_department': department.is_active = False
    elif change == 'inactive_leader': admin_user.is_active = False; admin_user.save()
    elif change == 'self': department.leader = member_user
    elif change == 'cycle': department.parent = department
    elif change == 'duplicate': OrganizationAppointment.objects.create(user=member_user, department=department, kind='primary', starts_on=day, reason='非法重复数据')
    record.save(); department.save()
    with pytest.raises(ValidationError):
        department_leader(ApprovalRequest(applicant=member_user), 2 if change == 'cycle' else 1)


def test_tenant_isolation_and_module_disabled(admin_user, member_user, settings):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    a = Tenant.objects.create(name='A', slug='a'); b = Tenant.objects.create(name='B', slug='b')
    TenantMembership.objects.create(tenant=a, user=member_user)
    department = Department.objects.create(name='D', tenant=a, leader=admin_user)
    OrganizationAppointment.objects.create(user=member_user, department=department, kind='primary', starts_on=timezone.localdate(), tenant=a, reason='入职')
    app = ApprovalRequest(applicant=member_user, tenant=a)
    with tenant_context(a.pk):
        with pytest.raises(ValidationError, match='有效成员'): department_leader(app, 1)
        TenantMembership.objects.create(tenant=a, user=admin_user)
        assert department_leader(app, 1)[0] == admin_user
    with tenant_context(b.pk):
        with pytest.raises(ValidationError): department_leader(ApprovalRequest(applicant=member_user, tenant=b), 1)
    settings.ADMINCORE_MODULES = ('approvals',)
    with pytest.raises(ValidationError, match='组织模块'): department_leader(app, 1)


@pytest.mark.parametrize('state', ['planned', 'active', 'ended', 'cancelled'])
def test_history_status_uses_server_effective_day(admin_client, member_user, state):
    from datetime import date
    day = date(2026, 10, 18)
    department = Department.objects.create(name='D')
    row = OrganizationAppointment.objects.create(user=member_user, department=department, kind='primary',
        starts_on=day + timedelta(days=1) if state == 'planned' else day - timedelta(days=1),
        ends_on=day if state == 'ended' else None, cancelled=state == 'cancelled', reason='测试')
    with patch('apps.core.appointment_views.timezone.localdate', return_value=day):
        response = admin_client.get(f'{BASE}{row.pk}/')
    assert response.status_code == 200 and response.json()['data']['status'] == state


def test_missing_next_supervisor_rolls_back_current_decision(admin_client, admin_user):
    department = Department.objects.create(name='D')
    OrganizationMembership.objects.create(user=admin_user, department=department)
    definition = flow_definition()
    definition['nodes'].insert(1, {'id': 'first', 'type': 'user', 'assignee': {'source': 'applicant'}})
    definition['edges'] = [{'from': 'start', 'to': 'first'}, {'from': 'first', 'to': 'review'}, {'from': 'review', 'to': 'end'}]
    flow = ApprovalFlow.objects.create(name='多级主管', code='leader-next', status='published', definition=definition, created_by=admin_user)
    response = admin_client.post('/api/v1/approvals/', {'title': '等待主管', 'content': '正文', 'flow_id': str(flow.pk)}, format='json')
    assert response.status_code == 201
    row = ApprovalRequest.objects.get(pk=response.json()['data']['id'])
    url = f'/api/v1/approvals/{row.pk}/approve/'
    assert admin_client.post(url, {}, format='json').status_code == 409
    row.refresh_from_db()
    assert row.current_node == 'first' and row.steps.get().status == 'pending'
    department.leader = get_user_model().objects.create_user('valid-next-leader'); department.save()
    moved = admin_client.post(url, {}, format='json')
    assert moved.status_code == 200 and moved.json()['data']['current_node'] == 'review'


@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_primary_appointments_have_one_winner():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connection
    if connection.vendor != 'postgresql':
        pytest.skip('行锁并发需要真实 PostgreSQL')
    user = get_user_model().objects.create_user('concurrent-employee')
    actors = [get_user_model().objects.create_superuser(f'concurrent-admin-{index}', password='OnlyTesting#4412') for index in range(2)]
    departments = [Department.objects.create(name=f'D{index}') for index in range(2)]
    barrier = Barrier(2)
    def create(pair):
        actor, department = pair
        close_old_connections()
        try:
            client = APIClient(); client.force_authenticate(get_user_model().objects.get(pk=actor.pk))
            barrier.wait(timeout=10)
            return client.post(BASE, payload(user, department), format='json').status_code
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, zip(actors, departments)))
    assert sorted(results) == [201, 400]
    assert OrganizationAppointment.objects.filter(user=user).count() == 1
