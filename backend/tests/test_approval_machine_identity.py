"""机器身份仅用于机器 API，不能进入人工审批及历史错误分配的处理链。"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.approvals.availability import exception_queryset
from apps.approvals.diagnostics import diagnose
from apps.approvals.graph import resolve_assignment
from apps.approvals.models import ApprovalAction, ApprovalRequest, ApprovalStep
from apps.approvals.tasks import available_user, scan_overdue
from apps.core.models import OutboxEvent
from apps.permissions.models import Role, UserRole
from tests.test_approval_operations import act, chain, client, publish, submit

pytestmark = pytest.mark.django_db


@pytest.fixture
def machine():
    return get_user_model().objects.create_user('approval-machine', password=None, is_service_account=True)


@pytest.mark.parametrize('field', ['assignee_id', 'assignee_username'])
def test_manual_submission_rejects_machine_without_side_effects(admin_client, machine, field):
    before = (ApprovalRequest.objects.count(), OutboxEvent.objects.count())
    target = str(machine.pk) if field == 'assignee_id' else machine.username
    response = admin_client.post('/api/v1/approvals/', {
        'title': '人员边界', 'content': '有效内容', field: target}, format='json')
    assert response.status_code == 400, response.content
    assert (ApprovalRequest.objects.count(), OutboxEvent.objects.count()) == before


@pytest.mark.parametrize('source', ['explicit', 'role', 'applicant', 'department_leader'])
def test_every_assignment_source_excludes_machine(admin_user, member_user, machine, monkeypatch, source):
    application = ApprovalRequest(applicant=admin_user, assignee=admin_user)
    node = {'id': 'review', 'type': 'user', 'assignee_ids': [str(machine.pk)]}
    if source == 'role':
        role = Role.objects.create(name='审批机器混合角色')
        UserRole.objects.create(user=machine, role=role)
        node = {'assignee': {'source': 'role', 'role_id': str(role.pk)}}
    elif source == 'applicant':
        application.applicant = machine
        node = {'assignee': {'source': 'applicant'}}
    elif source == 'department_leader':
        monkeypatch.setattr('apps.core.appointments.department_leader', lambda *_: (machine, {}))
        node = {'assignee': {'source': 'department_leader', 'levels': 1}}
    with pytest.raises(ValidationError):
        resolve_assignment(application, node)
    if source == 'role':
        UserRole.objects.create(user=member_user, role=role)
        people, _ = resolve_assignment(application, node)
        assert people == [member_user]


def test_published_frozen_machine_assignment_fails_atomically(admin_client, admin_user, machine):
    # 可发布的历史定义也必须在实际进入节点时重新验证人员，不能产生半张单。
    flow = publish(admin_client, chain(machine, admin_user))
    before = (ApprovalRequest.objects.count(), ApprovalStep.objects.count(), OutboxEvent.objects.count())
    response = admin_client.post('/api/v1/approvals/', {
        'title': '旧定义', 'content': '有效内容', 'flow_id': flow['id']}, format='json')
    assert response.status_code == 400, response.content
    assert (ApprovalRequest.objects.count(), ApprovalStep.objects.count(), OutboxEvent.objects.count()) == before


def test_future_machine_assignment_warns_without_leaking_identity(admin_client, admin_user, machine):
    app = submit(admin_client, publish(admin_client, chain(admin_user, machine)))
    response = admin_client.get(f"/api/v1/approvals/{app['id']}/diagnostics/")
    assert response.status_code == 200, response.content
    assert response.json()['data']['issues'] == [{'code': 'future_assignment_unavailable',
        'severity': 'warning', 'node': 'second', 'step_id': None, 'step_version': None}]
    assert machine.username not in response.content.decode()
    assert str(machine.pk) not in response.content.decode()


def test_machine_escalation_recipient_cannot_be_published(admin_client, admin_user, machine):
    definition = chain(admin_user, timeout={'minutes': 30, 'escalate_after_minutes': 60,
        'escalate_to': str(machine.pk)})
    response = admin_client.post('/api/v1/approvals/flows/', {
        'name': '升级人员边界', 'code': 'machine-escalation', 'definition': definition}, format='json')
    assert response.status_code == 201, response.content
    flow = response.json()['data']
    response = admin_client.post(f"/api/v1/approvals/flows/{flow['id']}/publish/", {'version': flow['version']}, format='json')
    assert response.status_code == 400, response.content


@pytest.mark.parametrize('operation', ['delegate', 'transfer', 'add-sign', 'cc', 'repair-step'])
def test_manual_participant_operations_reject_machine(admin_client, admin_user, machine, operation):
    app = submit(admin_client, publish(admin_client, chain(admin_user)))
    step = app['steps'][0]
    before = (ApprovalAction.objects.count(), ApprovalStep.objects.count(), OutboxEvent.objects.count())
    response = act(admin_client, app, operation, target_user_id=str(machine.pk),
        user_ids=[str(machine.pk)],
        step_id=step['id'], expected_version=step['version'], expected_workflow_version=app['workflow_version'])
    assert response.status_code == 400, response.content
    assert (ApprovalAction.objects.count(), ApprovalStep.objects.count(), OutboxEvent.objects.count()) == before
    assert ApprovalRequest.objects.get(pk=app['id']).workflow_version == app['workflow_version']


@pytest.mark.parametrize('broken', ['legacy', 'assignee', 'delegate'])
def test_historical_machine_assignment_is_diagnosed_and_repaired(admin_client, admin_user, member_user, machine, broken):
    if broken == 'legacy':
        application = ApprovalRequest.objects.create(title='历史旧单', content='有效内容',
            applicant=admin_user, assignee=machine)
        data = {'target_user_id': str(member_user.pk), 'expected_workflow_version': application.workflow_version}
    else:
        app = submit(admin_client, publish(admin_client, chain(member_user)))
        application = ApprovalRequest.objects.get(pk=app['id'])
        step = application.steps.get(status='pending')
        if broken == 'assignee':
            ApprovalStep.objects.filter(pk=step.pk).update(assignee=machine)
            ApprovalRequest.objects.filter(pk=application.pk).update(assignee=machine)
            application.refresh_from_db()
        else:
            ApprovalStep.objects.filter(pk=step.pk).update(delegated_to=machine)
        data = {'target_user_id': str(member_user.pk), 'step_id': str(step.pk),
                'expected_version': step.version, 'expected_workflow_version': application.workflow_version}
    codes = {row['code'] for row in diagnose(application)}
    assert ('delegate_unavailable' if broken == 'delegate' else 'assignee_unavailable') in codes
    assert exception_queryset(ApprovalRequest.objects.all()).filter(pk=application.pk).exists()
    assert available_user(machine.pk, application) is None
    response = act(admin_client, {'id': str(application.pk)}, 'repair-step', **data)
    assert response.status_code == 200, response.content
    application.refresh_from_db()
    assert application.assignee_id == member_user.pk
    assert not exception_queryset(ApprovalRequest.objects.all()).filter(pk=application.pk).exists()
    if broken != 'legacy':
        step.refresh_from_db()
        assert step.assignee_id == member_user.pk and step.delegated_to_id is None
        assert step.version == data['expected_version'] + 1


def test_historical_machine_timeout_recipients_are_unavailable_and_cannot_be_retried_as_target(admin_client, admin_user, machine):
    app = submit(admin_client, publish(admin_client, chain(admin_user)))
    application = ApprovalRequest.objects.get(pk=app['id'])
    step = application.steps.get(status='pending')
    past = timezone.now() - timedelta(minutes=1)
    ApprovalStep.objects.filter(pk=step.pk).update(delegated_to=machine, escalation_user=machine,
        due_at=past, escalate_at=past)
    before = OutboxEvent.objects.count()
    assert scan_overdue() == {'processed': 2, 'unavailable': 2}
    assert OutboxEvent.objects.count() == before
    codes = {row['code'] for row in diagnose(application)}
    assert {'delegate_unavailable', 'reminder_recipient_unavailable', 'escalation_recipient_unavailable', 'timeout_delivery_failed'} <= codes
    step.refresh_from_db()
    response = act(admin_client, app, 'retry-timeout', target_user_id=str(machine.pk),
        step_id=str(step.pk), expected_version=step.version, comment='改正升级人员')
    assert response.status_code == 404, response.content
    step.refresh_from_db()
    assert step.timeout_error == 'escalate,remind'
    assert scan_overdue() == {'processed': 0, 'unavailable': 0}


@pytest.mark.parametrize('workflow', [False, True])
def test_machine_cannot_process_corrupted_historical_assignment(admin_client, admin_user, machine, workflow):
    if workflow:
        app = submit(admin_client, publish(admin_client, chain(admin_user)))
        application = ApprovalRequest.objects.get(pk=app['id'])
        application.steps.update(assignee=machine)
        ApprovalRequest.objects.filter(pk=application.pk).update(assignee=machine)
    else:
        application = ApprovalRequest.objects.create(title='历史旧单', content='有效内容',
            applicant=admin_user, assignee=machine)
    before = (ApprovalAction.objects.count(), OutboxEvent.objects.count())
    response = act(client(machine), {'id': str(application.pk)}, expected_workflow_version=application.workflow_version)
    assert response.status_code in {401, 403}, response.content
    application.refresh_from_db()
    assert application.status == 'pending'
    assert (ApprovalAction.objects.count(), OutboxEvent.objects.count()) == before
