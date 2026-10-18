"""Read-only administrator diagnostics; never include business inputs or recipient identities."""
from django.core.exceptions import ValidationError as ModelValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .graph import next_node, resolve_assignment
from .models import validate_flow_definition


def diagnose(application, *, future=True):
    issues = []

    def add(code, severity='warning', node='', step=None):
        issues.append({'code': code, 'severity': severity, 'node': node,
                       'step_id': str(step.pk) if step else None, 'step_version': step.version if step else None})

    if application.status != 'pending':
        return issues
    steps = list(application.steps.filter(status='pending').order_by('sequence', 'pk'))
    identifiers = {application.applicant_id, application.assignee_id}
    for step in steps:
        identifiers.update((step.assignee_id, step.delegated_to_id, step.escalation_user_id))
    users = get_user_model().objects.filter(pk__in=identifiers - {None}, is_active=True, is_service_account=False)
    from apps.core.tenancy import enabled
    if enabled():
        users = users.filter(tenant_memberships__tenant_id=application.tenant_id,
            tenant_memberships__is_active=True, tenant_memberships__tenant__status='active') if application.tenant_id else users.none()
    available = {row[0]: row[1] for row in users.values_list('pk', 'must_change_password')}
    def can_act(identifier):
        return identifier in available and not available[identifier]
    if application.applicant_id not in available:
        add('applicant_unavailable')
    if application.flow_id:
        current = [step for step in steps if step.node_key == application.current_node]
        if not current:
            add('pending_step_missing', 'blocked', application.current_node)
        if len({step.sequence for step in current}) > 1 or any(step.node_key != application.current_node for step in steps):
            add('pending_step_mismatch', 'blocked', application.current_node)
    else:
        if not can_act(application.assignee_id):
            add('assignee_password_required' if application.assignee_id in available else 'assignee_unavailable', 'blocked')
        current = []
    if current:
        usable = []
        for step in current:
            assignee = can_act(step.assignee_id)
            delegate = bool(step.delegated_to_id and can_act(step.delegated_to_id))
            usable.append(assignee or delegate)
            if not assignee:
                add('assignee_password_required' if step.assignee_id in available else 'assignee_unavailable', 'warning' if delegate else 'blocked' if step.mode == 'all' else 'warning', step.node_key, step)
            if step.delegated_to_id and not delegate:
                add('delegate_unavailable', node=step.node_key, step=step)
            # Notifications follow the delegate when one is configured, even if the original
            # assignee can still decide. Password rotation does not disable notification receipt.
            if step.due_at and (step.delegated_to_id or step.assignee_id) not in available:
                add('reminder_recipient_unavailable', node=step.node_key, step=step)
            if step.escalate_at and step.escalation_user_id not in available:
                add('escalation_recipient_unavailable', node=step.node_key, step=step)
            if step.timeout_error:
                add('timeout_delivery_failed', node=step.node_key, step=step)
        if not any(usable):
            add('no_available_reviewer', 'blocked', application.current_node)
        now = timezone.now()
        if any(step.due_at and step.due_at <= now for step in current):
            add('overdue', node=application.current_node)
    if application.business_module:
        from apps.core.modules import module_enabled
        if not module_enabled(application.business_module):
            add('business_module_unavailable', 'blocked')
    if not application.flow_id:
        return issues
    definition = application.flow.definition
    try:
        from .engine import input_data
        validate_flow_definition(definition)
        data = input_data(definition, application.extra_data)
        nodes = {node['id']: node for node in definition['nodes']}
        node = nodes[application.current_node]
        if node['type'] not in {'user', 'parallel', 'or'}:
            raise ValueError
        if future:
            for _ in range(100):
                node = nodes[next_node(definition, node['id'], data)]
                if node['type'] == 'end':
                    break
                if node['type'] in {'user', 'parallel', 'or'}:
                    try:
                        resolve_assignment(application, node)
                    except ValidationError:
                        add('future_assignment_unavailable', node=node['id'])
            else:
                raise ValueError
    except (ModelValidationError, ValidationError, KeyError, TypeError, ValueError):
        # Do not echo validation details: they may contain frozen business inputs.
        add('flow_state_invalid', 'blocked')
    return issues
