from copy import deepcopy
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.approvals.calendar import deadline, validate_calendar
from apps.approvals.diagnostics import diagnose
from apps.approvals.models import ApprovalRequest, ApprovalStep
from apps.core.models import OutboxEvent
from tests.test_approval_operations import chain, publish, submit, act


def calendar(**changes):
    return {'timezone': 'Asia/Shanghai', 'weekdays': [1, 2, 3, 4, 5], 'start': '09:00',
            'end': '18:00', 'closed_dates': [], 'extra_dates': [], **changes}


def local(value, zone='Asia/Shanghai'):
    return datetime.fromisoformat(value).replace(tzinfo=ZoneInfo(zone))


@pytest.mark.parametrize('start,minutes,expected', [
    ('2026-10-16T17:30', 90, '2026-10-19T10:00'),
    ('2026-10-16T18:00', 60, '2026-10-19T10:00'),
    ('2026-10-19T07:00', 60, '2026-10-19T10:00'),
    ('2026-10-19T17:00', 60, '2026-10-19T18:00'),
    ('2028-02-28T17:00', 120, '2028-02-29T10:00'),
])
def test_working_deadlines(start, minutes, expected):
    assert deadline(local(start), minutes, calendar()) == local(expected)


def test_calendar_holidays_makeup_and_cross_timezone():
    configured = calendar(closed_dates=['2026-10-19'], extra_dates=['2026-10-17'])
    assert deadline(local('2026-10-16T17:30'), 90, configured) == local('2026-10-17T10:00')
    assert deadline(local('2026-10-17T17:30').astimezone(timezone.utc), 90, configured) == local('2026-10-20T10:00')
    now = local('2026-10-16T17:30')
    assert deadline(now, 90) == now + timedelta(minutes=90)


@pytest.mark.parametrize('start,minutes,expected', [
    ('2026-03-08T01:00', 120, '2026-03-08T04:00'), # one real hour disappears
    ('2026-11-01T01:00', 240, '2026-11-01T04:00'), # repeated hour counts twice
])
def test_dst_elapsed_time_inside_work_windows(start, minutes, expected):
    zone = 'America/New_York'
    value = calendar(timezone=zone, weekdays=[7], start='01:00', end='04:00')
    assert deadline(local(start, zone), minutes, value) == local(expected, zone)


def test_nonexistent_start_and_skipped_calendar_day():
    zone = 'America/New_York'
    value = calendar(timezone=zone, weekdays=[7], start='02:00', end='04:00')
    assert deadline(local('2026-03-08T01:00', zone), 60, value) == local('2026-03-08T04:00', zone)
    zone = 'Pacific/Apia'
    value = calendar(timezone=zone, weekdays=[5, 6], start='09:00', end='18:00')
    assert deadline(local('2011-12-29T18:00', zone), 60, value) == local('2011-12-31T10:00', zone)


@pytest.mark.parametrize('changes', [
    {'weekdays': [True]}, {'weekdays': []}, {'weekdays': [1, 1]}, {'timezone': 'unknown/place'},
    {'start': '23:00', 'end': '01:00'}, {'start': '09:01', 'end': '10:00'},
    {'closed_dates': ['2026-02-30']}, {'closed_dates': ['2026-10-19'] * 2},
    {'closed_dates': ['2026-10-19'], 'extra_dates': ['2026-10-19']},
    {'extra_dates': ['2026-1-1']}, {'unknown': 3},
])
def test_invalid_calendars(changes):
    with pytest.raises(ValidationError):
        validate_calendar(calendar(**changes))


def test_longest_supported_duration_is_bounded_and_date_overflow_is_controlled():
    value = calendar(weekdays=[1], start='09:00', end='10:00')
    assert deadline(local('2026-10-19T09:00'), 525600, value) < local('2195-01-01T00:00')
    with pytest.raises(ValidationError):
        deadline(local('9999-12-31T23:00'), 60, value)


@pytest.mark.django_db
def test_calendar_frozen_by_release_and_scanner_respects_working_deadline(admin_client, admin_user, monkeypatch):
    from apps.approvals.tasks import scan_overdue
    instant = local('2026-10-16T17:30')
    monkeypatch.setattr('django.utils.timezone.now', lambda: instant)
    definition = chain(admin_user, timeout={'minutes': 90, 'calendar': calendar()})
    original = publish(admin_client, definition)
    app = submit(admin_client, original)
    assert ApprovalStep.objects.get(request_id=app['id']).due_at == local('2026-10-19T10:00')
    draft = admin_client.post(f"/api/v1/approvals/flows/{original['id']}/new-revision/", {}, format='json').json()['data']
    changed = deepcopy(definition)
    changed['nodes'][1]['timeout']['calendar']['extra_dates'] = ['2026-10-17']
    update = admin_client.put(f"/api/v1/approvals/flows/{draft['id']}/", {
        'name': draft['name'], 'code': draft['code'], 'definition': changed, 'version': 1}, format='json')
    assert update.status_code == 200, update.content
    assert admin_client.post(f"/api/v1/approvals/flows/{draft['id']}/publish/", {'version': 2}, format='json').status_code == 200
    newer = submit(admin_client, draft)
    assert ApprovalStep.objects.get(request_id=newer['id']).due_at == local('2026-10-17T10:00')
    instant = local('2026-10-17T10:00')
    assert scan_overdue()['processed'] == 1
    assert not ApprovalStep.objects.get(request_id=app['id']).reminded_at
    # Returning to the archived node recomputes against its own frozen calendar.
    progressed = act(admin_client, app).json()['data']
    returned = act(admin_client, progressed, 'return-node', target_node='first',
        expected_workflow_version=progressed['workflow_version'], comment='复核')
    assert returned.status_code == 200, returned.content
    assert ApprovalStep.objects.get(request_id=app['id'], status='pending').due_at == local('2026-10-19T10:30')


@pytest.mark.django_db
def test_diagnostics_admin_only_no_side_effects_and_future_missing_actor(admin_client, member_client, admin_user, member_user):
    app = submit(admin_client, publish(admin_client, chain(admin_user, member_user)))
    member_user.is_active = False
    member_user.save(update_fields=['is_active'])
    request = ApprovalRequest.objects.get(pk=app['id'])
    before = (request.actions.count(), OutboxEvent.objects.count(), request.workflow_version)
    url = f"/api/v1/approvals/{app['id']}/diagnostics/"
    assert member_client.get(url).status_code == 401  # inactive authenticated actor
    response = admin_client.get(url)
    assert response.status_code == 200, response.content
    data = response.json()['data']
    assert data['scope'] == 'current_and_future' and not data['blocked']
    assert data['issues'] == [{'code': 'future_assignment_unavailable', 'severity': 'warning', 'node': 'second', 'step_id': None, 'step_version': None}]
    assert response['Cache-Control'] == 'private, no-store'
    assert 'member' not in response.content.decode() and '说明' not in response.content.decode()
    assert (request.actions.count(), OutboxEvent.objects.count(), request.workflow_version) == before
    member_user.is_active = True
    member_user.save(update_fields=['is_active'])
    from tests.test_approval_operations import client
    assert client(member_user).get(url).status_code == 403
    assert client(member_user).get('/api/v1/approvals/health/').status_code == 403


@pytest.mark.django_db
def test_current_all_any_delegate_password_and_bounded_actor_queries(admin_client, admin_user, member_user):
    app = submit(admin_client, publish(admin_client, chain(member_user)))
    request = ApprovalRequest.objects.get(pk=app['id'])
    step = request.steps.get()
    member_user.must_change_password = True
    member_user.save(update_fields=['must_change_password'])
    assert any(row['severity'] == 'blocked' for row in diagnose(request))
    step.delegated_to = admin_user
    step.save()
    assert not any(row['severity'] == 'blocked' for row in diagnose(request))
    # Many signers do not cause one actor lookup per step.
    for index in range(25):
        signer = get_user_model().objects.create(username=f'calendar-signer-{index}')
        ApprovalStep.objects.create(request=request, node_key='first', assignee=signer, sequence=0, mode='all')
    with CaptureQueriesContext(connection) as queries:
        diagnose(request, future=False)
    assert len(queries) <= 4
    request.steps.filter(status='pending').update(status='cancelled')
    assert 'pending_step_missing' in [row['code'] for row in diagnose(request)]


@pytest.mark.django_db
def test_health_cursor_validation_tenant_scope_and_no_future_leak(admin_user, member_user, settings):
    from apps.core.models import Tenant, TenantMembership
    from apps.core.tenancy import tenant_context
    from tests.test_approval_operations import client
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    first = Tenant.objects.create(name='甲', slug='calendar-a')
    second = Tenant.objects.create(name='乙', slug='calendar-b')
    membership = TenantMembership.objects.create(tenant=first, user=member_user)
    api = client(admin_user)
    ids = []
    for tenant in [first, first, second]:
        with tenant_context(tenant.pk):
            row = ApprovalRequest.objects.create(title='秘密', content='隐藏', applicant=member_user, assignee=member_user)
            ids.append(str(row.pk))
    membership.is_active = False
    membership.save()
    header = {'HTTP_X_ADMINCORE_TENANT': str(first.pk)}
    seen = []
    cursor = ''
    for _ in range(2):
        response = api.get('/api/v1/approvals/health/?limit=1' + cursor, **header)
        assert response.status_code == 200, response.content
        data = response.json()['data']
        assert data['scanned'] == 1 and data['items'][0]['blocked']
        assert data['items'][0]['scope'] == 'current'
        seen.append(data['items'][0]['request_id'])
        cursor = '&cursor=' + data['next_cursor'] if data['next_cursor'] else ''
    assert set(seen) == set(ids[:2]) and not cursor
    assert api.get(f'/api/v1/approvals/{ids[2]}/diagnostics/', **header).status_code == 404
    for query in ['limit=0', 'limit=101', 'limit=true', 'limit=1&limit=2', 'cursor=bad', 'other=1']:
        assert api.get('/api/v1/approvals/health/?' + query, **header).status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize('workflow', [False, True])
def test_revoked_member_repair_is_current_versioned_and_scoped(admin_user, member_user, settings, workflow):
    from apps.core.models import Tenant, TenantMembership
    from apps.core.tenancy import tenant_context
    from tests.test_approval_operations import client
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    tenant = Tenant.objects.create(name='修复租户', slug='repair-tenant')
    other = Tenant.objects.create(name='他租户', slug='repair-other')
    TenantMembership.objects.create(tenant=tenant, user=admin_user)
    member = TenantMembership.objects.create(tenant=tenant, user=member_user)
    outside = get_user_model().objects.create(username='outside-repair')
    TenantMembership.objects.create(tenant=other, user=outside)
    api = client(admin_user)
    header = {'HTTP_X_ADMINCORE_TENANT': str(tenant.pk)}
    if workflow:
        definition = chain(member_user)
        response = api.post('/api/v1/approvals/flows/', {'name': '修复流程', 'code': 'repair', 'definition': definition}, format='json', **header)
        assert response.status_code == 201, response.content
        flow = response.json()['data']
        assert api.post(f"/api/v1/approvals/flows/{flow['id']}/publish/", {'version': flow['version']}, format='json', **header).status_code == 200
        response = api.post('/api/v1/approvals/', {'title': '修复', 'content': '成员调整', 'flow_id': flow['id']}, format='json', **header)
        assert response.status_code == 201, response.content
        row = ApprovalRequest.objects.get(pk=response.json()['data']['id'])
        step = row.steps.get()
        payload = {'step_id': str(step.pk), 'expected_version': step.version}
        step.delegated_to = admin_user
        step.save()
    else:
        with tenant_context(tenant.pk):
            row = ApprovalRequest.objects.create(title='旧单修复', applicant=admin_user, assignee=member_user)
        payload = {'expected_workflow_version': row.workflow_version}
    member.is_active = False
    member.save()
    url = f'/api/v1/approvals/{row.pk}/repair-step/'
    payload.update(target_user_id=str(admin_user.pk), comment='成员离职改派')
    assert api.get('/api/v1/approvals/health/').status_code == 403
    assert api.get(f'/api/v1/approvals/{row.pk}/diagnostics/').status_code == 403
    assert api.post(url, payload, format='json').status_code == 403
    response = api.get('/api/v1/approvals/?box=exceptions', **header)
    assert response.status_code == 200, response.content
    assert str(row.pk) in str(response.json())
    invalid = api.post(url, {**payload, 'target_user_id': str(outside.pk)}, format='json', **header)
    assert invalid.status_code == 400, invalid.content
    assert client(member_user).post(url, payload, format='json', **header).status_code == 403
    assert api.post(url, payload, format='json', HTTP_X_ADMINCORE_TENANT=str(other.pk)).status_code in {400, 404}
    before = OutboxEvent.objects.count()
    response = api.post(url, payload, format='json', **header)
    assert response.status_code == 200, response.content
    row.refresh_from_db()
    assert row.assignee_id == admin_user.pk and row.actions.filter(action='transfer').count() == 1
    assert OutboxEvent.objects.count() == before + 1
    if workflow:
        step.refresh_from_db()
        assert step.assignee_id == admin_user.pk and step.delegated_to_id is None
    stale = api.post(url, payload, format='json', **header)
    assert stale.status_code == 409, stale.content
    assert row.actions.filter(action='transfer').count() == 1
    healthy = api.post(url, {**payload, ('expected_version' if workflow else 'expected_workflow_version'): (step.version if workflow else row.workflow_version)}, format='json', **header)
    assert healthy.status_code == 400, healthy.content
    tenant.status = Tenant.STATUS_CLOSED
    tenant.save()
    assert api.get('/api/v1/approvals/health/', **header).status_code == 403


@pytest.mark.django_db
def test_invalid_delegate_can_only_be_cleared_back_to_valid_original(admin_client, admin_user, member_user):
    app = submit(admin_client, publish(admin_client, chain(admin_user)))
    row = ApprovalRequest.objects.get(pk=app['id'])
    step = row.steps.get()
    step.delegated_to = member_user
    step.save()
    member_user.is_active = False
    member_user.save()
    replacement = get_user_model().objects.create(username='replacement-delegate')
    url = f'/api/v1/approvals/{row.pk}/repair-step/'
    payload = {'target_user_id': str(replacement.pk), 'step_id': str(step.pk), 'expected_version': step.version, 'comment': '清除失效委托'}
    assert admin_client.post(url, payload, format='json').status_code == 400
    response = admin_client.post(url, {**payload, 'target_user_id': str(admin_user.pk)}, format='json')
    assert response.status_code == 200, response.content
    step.refresh_from_db()
    assert step.assignee_id == admin_user.pk and step.delegated_to_id is None


@pytest.mark.django_db
def test_repair_rejects_pending_step_outside_current_node_and_inactive_target(admin_client, admin_user, member_user):
    app = submit(admin_client, publish(admin_client, chain(member_user)))
    row = ApprovalRequest.objects.get(pk=app['id'])
    current = row.steps.get()
    future = ApprovalStep.objects.create(request=row, node_key='second', assignee=member_user, sequence=0, mode='all')
    member_user.is_active = False
    member_user.save(update_fields=['is_active'])
    before = (row.workflow_version, row.actions.count(), OutboxEvent.objects.count())
    url = f'/api/v1/approvals/{row.pk}/repair-step/'
    payload = {'target_user_id': str(admin_user.pk), 'step_id': str(future.pk), 'expected_version': future.version, 'comment': '仅修复当前节点'}
    assert admin_client.post(url, payload, format='json').status_code == 404
    payload.update(step_id=str(current.pk), expected_version=current.version, target_user_id=str(member_user.pk))
    assert admin_client.post(url, payload, format='json').status_code == 400
    row.refresh_from_db()
    assert (row.workflow_version, row.actions.count(), OutboxEvent.objects.count()) == before


@pytest.mark.django_db
def test_timeout_retry_requires_selected_tenant_current_node_and_available_recipient(admin_user, member_user, settings):
    from apps.approvals.models import ApprovalFlow
    from apps.core.models import Tenant, TenantMembership
    from apps.core.tenancy import tenant_context
    from tests.test_approval_operations import client
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    tenant = Tenant.objects.create(name='重试租户', slug='retry-tenant')
    other = Tenant.objects.create(name='其他重试租户', slug='retry-other')
    TenantMembership.objects.create(tenant=tenant, user=admin_user)
    TenantMembership.objects.create(tenant=tenant, user=member_user)
    outside = get_user_model().objects.create(username='outside-retry')
    TenantMembership.objects.create(tenant=other, user=outside)
    with tenant_context(tenant.pk):
        flow = ApprovalFlow.objects.create(name='重试流程', code='retry-flow', definition=chain(admin_user), status='published', created_by=admin_user)
        row = ApprovalRequest.objects.create(title='重试', content='说明', applicant=admin_user,
            assignee=admin_user, flow=flow, current_node='first')
        current = ApprovalStep.objects.create(request=row, node_key='first', assignee=admin_user,
            sequence=0, mode='all', timeout_error='escalate')
        future = ApprovalStep.objects.create(request=row, node_key='second', assignee=admin_user,
            sequence=0, mode='all', timeout_error='escalate')
    api = client(admin_user)
    header = {'HTTP_X_ADMINCORE_TENANT': str(tenant.pk)}
    url = f'/api/v1/approvals/{row.pk}/retry-timeout/'
    payload = {'step_id': str(current.pk), 'expected_version': current.version, 'comment': '升级接收人修复', 'target_user_id': str(admin_user.pk)}
    assert api.post(url, payload, format='json').status_code == 403
    assert client(member_user).post(url, payload, format='json', **header).status_code == 403
    assert api.post(url, {**payload, 'target_user_id': str(outside.pk)}, format='json', **header).status_code == 400
    assert api.post(url, {**payload, 'target_user_id': str(outside.pk)}, format='json', HTTP_X_ADMINCORE_TENANT=str(other.pk)).status_code == 404
    assert api.post(url, {**payload, 'step_id': str(future.pk)}, format='json', **header).status_code == 404
    TenantMembership.objects.filter(tenant=tenant, user=member_user).update(is_active=False)
    assert api.post(url, {**payload, 'target_user_id': str(member_user.pk)}, format='json', **header).status_code == 400
    assert row.actions.count() == 0
    response = api.post(url, payload, format='json', **header)
    assert response.status_code == 200, response.content
    current.refresh_from_db()
    assert current.timeout_error == '' and current.escalation_user_id == admin_user.pk
    assert api.post(url, payload, format='json', **header).status_code == 409
    assert row.actions.filter(action='retry_timeout').count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('workflow', [False, True])
def test_postgres_competing_repairs_commit_once(workflow):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connection
    from tests.test_approval_operations import client
    if connection.vendor != 'postgresql':
        pytest.skip('修复并发需要 PostgreSQL')
    actors = [get_user_model().objects.create_superuser(f'repair-race-{i}', password='OnlyTesting#4412') for i in range(2)]
    lost = get_user_model().objects.create(username='repair-race-lost')
    api = client(actors[0])
    if workflow:
        app = submit(api, publish(api, chain(lost)))
        row = ApprovalRequest.objects.get(pk=app['id'])
        step = row.steps.get()
        payload = {'step_id': str(step.pk), 'expected_version': step.version}
    else:
        row = ApprovalRequest.objects.create(title='并发修复', content='说明', applicant=actors[0], assignee=lost)
        payload = {'expected_workflow_version': row.workflow_version}
    lost.is_active = False
    lost.save()
    before_version = row.workflow_version
    barrier = Barrier(2)
    def run(actor):
        close_old_connections()
        try:
            local = client(get_user_model().objects.get(pk=actor.pk))
            barrier.wait(timeout=10)
            return local.post(f'/api/v1/approvals/{row.pk}/repair-step/', {**payload, 'target_user_id': str(actor.pk), 'comment': '并发修复'}, format='json').status_code
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, actors))
    assert sorted(results) == [200, 409]
    row.refresh_from_db()
    assert row.workflow_version == before_version + 1 and row.actions.filter(action='transfer').count() == 1
    assert OutboxEvent.objects.filter(event_key__startswith=f'approval:{row.pk}:').count() == (2 if workflow else 1)
