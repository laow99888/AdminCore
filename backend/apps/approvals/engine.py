"""节点推进由审批中心和已登记业务模块共用；调用方持有申请行锁。"""
from django.utils import timezone
from .graph import next_node, resolve_assignees, validate_inputs
from .models import ApprovalStep, validate_flow_definition
from django.core.exceptions import ValidationError as ModelValidationError
from rest_framework.exceptions import ValidationError


def input_data(definition, data):
    try:
        validate_flow_definition(definition)
        return validate_inputs(definition, data)
    except ModelValidationError as error:
        raise ValidationError(error.messages) from error


def enter_next(application, *, initial=False):
    definition = application.flow.definition
    data = input_data(definition, application.extra_data)
    nodes = {node['id']: node for node in definition['nodes']}
    current = next(node['id'] for node in definition['nodes'] if node['type'] == 'start') if initial else application.current_node
    for _ in range(100):
        target = nodes[next_node(definition, current, data)]
        current = target['id']
        if target['type'] == 'end':
            application.status = 'approved'
            application.decided_at = timezone.now()
            application.current_node = current
            application.save(update_fields=['status', 'decided_by', 'decided_at', 'current_node', 'updated_at'])
            return []
        if target['type'] in {'user', 'parallel', 'or'}:
            try:
                users = resolve_assignees(application, target)
            except ValidationError as error:
                if initial:
                    raise
                from apps.core.exceptions import APIError
                raise APIError(error.detail, status_code=409) from error
            sequence = max(application.steps.values_list('sequence', flat=True), default=-1) + 1
            for user in users:
                ApprovalStep.objects.create(request=application, node_key=current, kind=target['type'],
                    mode=target.get('mode', 'any' if target['type'] == 'or' else 'all'), sequence=sequence,
                    assignee=user, candidates=[str(row.pk) for row in users])
            application.current_node = current
            application.assignee = users[0]
            if not initial:
                application.workflow_version += 1
            application.save(update_fields=['current_node', 'assignee', 'workflow_version', 'updated_at'])
            return users
    raise RuntimeError('Validated workflow exceeded node limit')


def synchronize_business(application, request):
    if not application.business_module:
        return
    from apps.core.codegen.integrations import sync_approval
    sync_approval(application, request)
