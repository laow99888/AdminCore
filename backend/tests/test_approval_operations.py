"""通过公开 API 验证版本隔离、退回重办、超时去重和异常重试。"""
from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.approvals.models import ApprovalAction, ApprovalFlow, ApprovalRequest, ApprovalStep
from apps.approvals.tasks import scan_overdue
from apps.core.models import OutboxEvent

pytestmark = pytest.mark.django_db


def client(user):
    result = APIClient()
    result.force_authenticate(user)
    return result


def chain(user, other=None, timeout=None):
    nodes = [{'id': 'start', 'type': 'start'},
             {'id': 'first', 'type': 'user', 'assignee_ids': [str(user.pk)]},
             {'id': 'second', 'type': 'user', 'assignee_ids': [str((other or user).pk)]},
             {'id': 'end', 'type': 'end'}]
    if timeout:
        nodes[1]['timeout'] = timeout
    return {'schema_version': 2, 'inputs': [], 'nodes': nodes,
            'edges': [{'from': a, 'to': b} for a, b in [('start', 'first'), ('first', 'second'), ('second', 'end')]]}


def publish(api, definition):
    response = api.post('/api/v1/approvals/flows/', {'name': '采购审核', 'code': 'purchase', 'definition': definition}, format='json')
    assert response.status_code == 201, response.content
    flow = response.json()['data']
    response = api.post(f"/api/v1/approvals/flows/{flow['id']}/publish/", {'version': flow['version']}, format='json')
    assert response.status_code == 200, response.content
    return response.json()['data']


def submit(api, flow):
    response = api.post('/api/v1/approvals/', {'title': '采购', 'content': '说明', 'flow_id': flow['id']}, format='json')
    assert response.status_code == 201, response.content
    return response.json()['data']


def act(api, application, operation='approve', **payload):
    return api.post(f"/api/v1/approvals/{application['id']}/{operation}/", payload, format='json')


def test_release_replaces_head_but_preserves_inflight(admin_client, admin_user, member_user):
    original = publish(admin_client, chain(admin_user))
    old = submit(admin_client, original)
    clone_url = f"/api/v1/approvals/flows/{original['id']}/new-revision/"
    response = admin_client.post(clone_url, {}, format='json', HTTP_IDEMPOTENCY_KEY='release-copy')
    assert response.status_code == 201, response.content
    draft = response.json()['data']
    assert draft['code'] == original['code'] and draft['revision'] == 2 and draft['version'] == 1
    assert admin_client.post(clone_url, {}, format='json', HTTP_IDEMPOTENCY_KEY='release-copy')['Idempotency-Replayed'] == 'true'
    assert admin_client.post(clone_url, {}, format='json').status_code == 409
    assert submit(admin_client, original)['flow_revision'] == 1  # 草稿不影响现行版
    changed = chain(member_user)
    response = admin_client.put(f"/api/v1/approvals/flows/{draft['id']}/", {
        'name': draft['name'], 'code': draft['code'], 'definition': changed, 'version': 1}, format='json')
    assert response.status_code == 200, response.content
    assert response.json()['data']['version'] == 2
    assert admin_client.post(f"/api/v1/approvals/flows/{draft['id']}/publish/", {'version': 1}, format='json').status_code == 409
    assert admin_client.post(f"/api/v1/approvals/flows/{draft['id']}/publish/", {'version': 2}, format='json').status_code == 200
    assert ApprovalFlow.objects.get(pk=original['id']).status == 'archived'
    assert ApprovalFlow.objects.filter(code='purchase', status='published').count() == 1
    new = submit(admin_client, draft)
    assert new['flow_revision'] == 2 and new['steps'][0]['assignee'] == str(member_user.pk)
    assert admin_client.post('/api/v1/approvals/', {'title': '旧版', 'content': '说明', 'flow_id': original['id']}, format='json').status_code == 400
    # 在途第二节点依然使用原定义。
    response = act(admin_client, old)
    assert response.status_code == 200 and response.json()['data']['steps'][-1]['assignee'] == str(admin_user.pk)
    listed = admin_client.get('/api/v1/approvals/flows/?code=purchase&ordering=-revision').json()['data']['items']
    assert [row['revision'] for row in listed] == [2, 1]


def test_revision_authorization_and_immutable_code(admin_client, admin_user, member_client):
    flow = publish(admin_client, chain(admin_user))
    assert member_client.post(f"/api/v1/approvals/flows/{flow['id']}/new-revision/", format='json').status_code == 403
    assert member_client.get(f"/api/v1/approvals/flows/{flow['id']}/").status_code == 404
    draft = admin_client.post(f"/api/v1/approvals/flows/{flow['id']}/new-revision/", format='json').json()['data']
    response = admin_client.put(f"/api/v1/approvals/flows/{draft['id']}/", {
        'name': '改名', 'code': 'other', 'definition': chain(admin_user), 'version': 1}, format='json')
    assert response.status_code == 400
    assert admin_client.post(f"/api/v1/approvals/flows/{draft['id']}/new-revision/", format='json').status_code == 400


def test_return_repeats_nodes_without_overwriting_history(admin_client, admin_user):
    flow = publish(admin_client, chain(admin_user))
    original = submit(admin_client, flow)
    current = act(admin_client, original).json()['data']
    assert current['returnable_nodes'] == ['first']
    payload = {'target_node': 'first', 'expected_workflow_version': current['workflow_version'], 'comment': '请复核'}
    url = f"/api/v1/approvals/{original['id']}/return-node/"
    response = admin_client.post(url, payload, format='json', HTTP_IDEMPOTENCY_KEY='return-once')
    assert response.status_code == 200, response.content
    returned = response.json()['data']
    assert returned['current_node'] == 'first' and returned['return_count'] == 1
    assert [(s['sequence'], s['status']) for s in returned['steps']] == [(0, 'approved'), (1, 'cancelled'), (2, 'pending')]
    assert admin_client.post(url, payload, format='json', HTTP_IDEMPOTENCY_KEY='return-once')['Idempotency-Replayed'] == 'true'
    assert act(admin_client, returned).status_code == 400  # 旧客户端必须升级
    assert act(admin_client, returned, expected_workflow_version=current['workflow_version']).status_code == 409
    assert act(admin_client, returned, expected_workflow_version=returned['workflow_version'], step_id=original['steps'][0]['id']).status_code == 409
    response = act(admin_client, returned, expected_workflow_version=returned['workflow_version'], step_id=returned['steps'][-1]['id'])
    assert response.status_code == 200, response.content
    final_pending = response.json()['data']
    assert final_pending['current_node'] == 'second'
    assert act(admin_client, final_pending, expected_workflow_version=final_pending['workflow_version']).json()['data']['status'] == 'approved'
    history = admin_client.get(f"/api/v1/approvals/{original['id']}/history/").json()['data']
    assert history['pagination']['total'] == 4
    assert [row['action'] for row in history['items']].count('return') == 1


@pytest.mark.parametrize('target', ['second', 'end', 'missing'])
def test_return_rejects_unvisited_current_or_end(admin_client, admin_user, target):
    app = submit(admin_client, publish(admin_client, chain(admin_user)))
    app = act(admin_client, app).json()['data']
    response = act(admin_client, app, 'return-node', target_node=target, expected_workflow_version=app['workflow_version'], comment='复核')
    assert response.status_code == 400
    assert ApprovalRequest.objects.get(pk=app['id']).return_count == 0


def test_return_requires_reason_current_version_and_actor(admin_client, admin_user, member_user):
    flow = publish(admin_client, chain(admin_user, member_user))
    app = act(admin_client, submit(admin_client, flow)).json()['data']
    response = act(admin_client, app, 'return-node', target_node='first', expected_workflow_version=app['workflow_version'], comment='复核')
    assert response.status_code == 403
    assert act(client(member_user), app, 'return-node', target_node='first', comment='复核').status_code == 400
    assert act(client(member_user), app, 'return-node', target_node='first', expected_workflow_version=app['workflow_version'], comment=' ').status_code == 400


def test_return_assignment_failure_rolls_back_and_can_retry(admin_client, admin_user, member_user):
    flow = publish(admin_client, chain(member_user, admin_user))
    app = submit(admin_client, flow)
    app = act(client(member_user), app).json()['data']
    member_user.is_active = False
    member_user.save(update_fields=['is_active'])
    response = act(admin_client, app, 'return-node', target_node='first', expected_workflow_version=app['workflow_version'], comment='复核')
    assert response.status_code == 409
    assert ApprovalStep.objects.filter(request_id=app['id'], status='pending', node_key='second').count() == 1
    assert not ApprovalAction.objects.filter(request_id=app['id'], action='return').exists()
    member_user.is_active = True
    member_user.save(update_fields=['is_active'])
    assert act(admin_client, app, 'return-node', target_node='first', expected_workflow_version=app['workflow_version'], comment='复核').status_code == 200


def test_return_respects_all_signs_and_transfer_does_not_conflict_with_old_visit(admin_client, admin_user, member_user):
    definition = chain(admin_user)
    definition['nodes'][1].update(type='parallel', mode='all', assignee_ids=[str(admin_user.pk), str(member_user.pk)])
    app = submit(admin_client, publish(admin_client, definition))
    app = act(admin_client, app).json()['data']
    assert app['returnable_nodes'] == []
    app = act(client(member_user), app).json()['data']
    app = act(admin_client, app, 'return-node', target_node='first', expected_workflow_version=app['workflow_version'], comment='重新会签').json()['data']
    app = act(admin_client, app, expected_workflow_version=app['workflow_version']).json()['data']
    assert app['current_node'] == 'first'
    app = act(client(member_user), app, expected_workflow_version=app['workflow_version']).json()['data']
    assert app['current_node'] == 'second'


def test_overdue_deduplicates_and_preserves_state(admin_client, admin_user, member_user):
    timeout = {'minutes': 1, 'escalate_after_minutes': 2, 'escalate_to': str(member_user.pk)}
    app = submit(admin_client, publish(admin_client, chain(admin_user, timeout=timeout)))
    step = ApprovalStep.objects.get(request_id=app['id'])
    assert step.due_at and step.escalate_at > step.due_at
    ApprovalStep.objects.filter(pk=step.pk).update(due_at=timezone.now()-timedelta(minutes=2), escalate_at=timezone.now()-timedelta(minutes=1))
    assert scan_overdue() == {'processed': 2, 'unavailable': 0}
    assert scan_overdue() == {'processed': 0, 'unavailable': 0}
    assert ApprovalRequest.objects.get(pk=app['id']).status == 'pending'
    assert ApprovalAction.objects.filter(request_id=app['id'], actor__isnull=True).count() == 2
    events = OutboxEvent.objects.filter(event_key__contains=f':step:{step.pk}:')
    assert events.count() == 2
    assert all(event.payload['content'] == '' and event.payload['title'] != app['title'] for event in events)
    assert client(member_user).get(f"/api/v1/approvals/{app['id']}/").status_code == 404  # 提醒不扩展可见范围
    exceptions = admin_client.get('/api/v1/approvals/?box=exceptions').json()['data']['items']
    assert [row['id'] for row in exceptions] == [app['id']]


def test_overdue_unavailable_recipient_audited_and_admin_can_retry(admin_client, admin_user, member_user):
    timeout = {'minutes': 1, 'escalate_after_minutes': 2, 'escalate_to': str(member_user.pk)}
    app = submit(admin_client, publish(admin_client, chain(admin_user, timeout=timeout)))
    member_user.is_active = False
    member_user.save(update_fields=['is_active'])
    step = ApprovalStep.objects.get(request_id=app['id'])
    ApprovalStep.objects.filter(pk=step.pk).update(due_at=timezone.now()-timedelta(minutes=2), escalate_at=timezone.now()-timedelta(minutes=1))
    assert scan_overdue() == {'processed': 2, 'unavailable': 1}
    assert scan_overdue()['processed'] == 0
    step.refresh_from_db()
    assert step.timeout_error == 'escalate'
    assert act(admin_client, app, 'retry-timeout', step_id=str(step.pk), expected_version=step.version).status_code == 400
    response = act(admin_client, app, 'retry-timeout', step_id=str(step.pk), expected_version=step.version,
                   target_user_id=str(admin_user.pk), comment='更换值班接收人')
    assert response.status_code == 200, response.content
    assert scan_overdue() == {'processed': 1, 'unavailable': 0}
    step.refresh_from_db()
    assert step.timeout_error == '' and step.escalation_user_id == admin_user.pk
    assert act(admin_client, app, 'retry-timeout', step_id=str(step.pk), expected_version=step.version, comment='重复').status_code == 400


def test_completed_or_returned_steps_never_reminded(admin_client, admin_user):
    app = submit(admin_client, publish(admin_client, chain(admin_user, timeout={'minutes': 1})))
    ApprovalStep.objects.filter(request_id=app['id']).update(due_at=timezone.now()-timedelta(minutes=1))
    act(admin_client, app)
    assert scan_overdue()['processed'] == 0


@pytest.mark.parametrize('timeout', [{'minutes': True}, {'minutes': 0}, {'minutes': 525601},
    {'minutes': 1, 'other': 3}, {'minutes': 1, 'escalate_after_minutes': 2},
    {'minutes': 1, 'escalate_after_minutes': 1, 'escalate_to': str(uuid4())},
    {'minutes': 1, 'escalate_after_minutes': 2, 'escalate_to': 'x'}])
def test_timeout_definition_rejects_invalid_configuration(admin_client, admin_user, timeout):
    response = admin_client.post('/api/v1/approvals/flows/', {
        'name': '错误', 'code': 'bad', 'definition': chain(admin_user, timeout=timeout)}, format='json')
    assert response.status_code == 400


@pytest.mark.parametrize('limit', [0, 1001, True, '100'])
def test_scan_rejects_unbounded_batches(limit):
    with pytest.raises(ValueError):
        scan_overdue(limit)


def test_scan_module_switch(settings):
    from celery.exceptions import Ignore
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'approvals')
    with pytest.raises(Ignore):
        scan_overdue()


def test_schedule_is_installed_once_and_preserves_operator_changes():
    from io import StringIO
    from django.core.management import call_command
    from django_celery_beat.models import PeriodicTask
    call_command('configure_maintenance', stdout=StringIO())
    task = PeriodicTask.objects.get(task='approvals.scan_overdue')
    assert task.enabled and task.crontab.minute == '*' and task.crontab.hour == '*'
    task.enabled = False
    task.save()
    call_command('configure_maintenance', stdout=StringIO())
    assert not PeriodicTask.objects.get(pk=task.pk).enabled


def test_timeout_tenant_membership_rechecked_before_delivery(admin_user, member_user, settings):
    from apps.core.models import Tenant, TenantMembership
    from apps.core.tenancy import tenant_context
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    tenant = Tenant.objects.create(name='甲', slug='a')
    other = Tenant.objects.create(name='乙', slug='b')
    TenantMembership.objects.create(tenant=tenant, user=admin_user)
    TenantMembership.objects.create(tenant=other, user=member_user)
    with tenant_context(tenant.pk):
        flow = ApprovalFlow.objects.create(code='tenant-flow', name='租户', definition=chain(admin_user), created_by=admin_user)
        app = ApprovalRequest.objects.create(title='租户审批', content='内容', applicant=admin_user, assignee=admin_user,
            flow=flow, current_node='first')
        step = ApprovalStep.objects.create(request=app, node_key='first', assignee=admin_user,
            due_at=timezone.now()-timedelta(minutes=2), escalate_at=timezone.now()-timedelta(minutes=1), escalation_user=member_user)
    assert scan_overdue() == {'processed': 2, 'unavailable': 1}
    step.refresh_from_db()
    assert step.timeout_error == 'escalate'
    events = OutboxEvent.all_objects.filter(event_key__contains=f':step:{step.pk}:')
    assert events.count() == 1 and events.get().tenant_id == tenant.pk


@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_revisions_serialize():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connection
    if connection.vendor != 'postgresql':
        pytest.skip('版本行锁竞争需要 PostgreSQL')
    actors = [get_user_model().objects.create_superuser(f'release-admin-{i}', password='OnlyTesting#4412') for i in range(2)]
    flow = ApprovalFlow.objects.create(code='concurrent-flow', name='竞争', status='published',
        definition=chain(actors[0]), created_by=actors[0], published_at=timezone.now())
    barrier = Barrier(2)
    def run(actor):
        close_old_connections()
        try:
            api = client(get_user_model().objects.get(pk=actor.pk))
            barrier.wait(timeout=10)
            return api.post(f'/api/v1/approvals/flows/{flow.pk}/new-revision/', {}, format='json').status_code
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, actors))
    assert sorted(results) == [201, 409]
    assert list(ApprovalFlow.objects.filter(code=flow.code).order_by('revision').values_list('revision', flat=True)) == [1, 2]


@pytest.mark.django_db(transaction=True)
def test_postgres_competing_returns_create_one_new_visit():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connection
    if connection.vendor != 'postgresql':
        pytest.skip('退回并发需要 PostgreSQL')
    actors = [get_user_model().objects.create_superuser(f'return-admin-{i}', password='OnlyTesting#4412') for i in range(2)]
    definition = chain(actors[0])
    for node in definition['nodes'][1:3]:
        node.update(type='parallel', mode='all', assignee_ids=[str(actor.pk) for actor in actors])
    api = client(actors[0])
    app = submit(api, publish(api, definition))
    assert act(api, app).status_code == 200
    app = act(client(actors[1]), app).json()['data']
    barrier = Barrier(2)
    def run(actor):
        close_old_connections()
        try:
            local = client(get_user_model().objects.get(pk=actor.pk))
            barrier.wait(timeout=10)
            return act(local, app, 'return-node', target_node='first', expected_workflow_version=app['workflow_version'], comment='并发退回').status_code
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, actors))
    assert sorted(results) == [200, 409]
    request = ApprovalRequest.objects.get(pk=app['id'])
    assert request.return_count == 1 and request.steps.filter(status='pending', sequence=2).count() == 2


@pytest.mark.django_db(transaction=True)
def test_postgres_overlapping_scans_queue_once():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connection
    if connection.vendor != 'postgresql':
        pytest.skip('后台并发需要 PostgreSQL')
    actor = get_user_model().objects.create_superuser('scan-admin', password='OnlyTesting#4412')
    api = client(actor)
    app = submit(api, publish(api, chain(actor, timeout={'minutes': 1, 'escalate_after_minutes': 2, 'escalate_to': str(actor.pk)})))
    ApprovalStep.objects.filter(request_id=app['id']).update(due_at=timezone.now()-timedelta(minutes=2), escalate_at=timezone.now()-timedelta(minutes=1))
    barrier = Barrier(2)
    def run(_):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return scan_overdue()
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sum(result['processed'] for result in results) == 2
    assert ApprovalAction.objects.filter(request_id=app['id'], action__in=['remind', 'escalate']).count() == 2


@pytest.mark.django_db(transaction=True)
def test_postgres_authorization_lock_allows_references_but_blocks_revocation():
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    from django.db import OperationalError, close_old_connections, connection, transaction
    from apps.auth_app.write_authorization import authorize_write
    if connection.vendor != 'postgresql':
        pytest.skip('授权锁相容性需要 PostgreSQL')
    actor = get_user_model().objects.create_superuser('lock-actor', password='OnlyTesting#4412')
    def probe():
        close_old_connections()
        try:
            # 非主键外键引用可以共存；撤权所需的更新锁仍须等待。
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute('SELECT id FROM auth_app_user WHERE id = %s FOR KEY SHARE NOWAIT', [actor.pk])
            try:
                with transaction.atomic():
                    get_user_model().objects.select_for_update(nowait=True).get(pk=actor.pk)
            except OperationalError as error:
                return getattr(error.__cause__, 'pgcode', None)
            return 'unexpectedly_unlocked'
        finally:
            close_old_connections()
    with transaction.atomic():
        authorize_write(SimpleNamespace(user=actor, auth=None))
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(probe).result(timeout=10) == '55P03'
