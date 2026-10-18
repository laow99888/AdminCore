"""流程版本与退回规则；调用方须先完成写授权并持有申请或流程根版本锁。"""
from collections import defaultdict
from copy import deepcopy

from django.db.models import Max
from rest_framework.exceptions import ValidationError

from apps.core.exceptions import APIError
from .models import ApprovalFlow


def audit_flow(request, flow, action):
    from apps.logs.audit import snapshot, write_audit
    write_audit(request=request, resource='approval_flow', identifier=flow.pk, action=action,
                after=snapshot('approval_flow', flow))


def lock_series(flow):
    # 所有发布、归档、新版本操作按同一根行串行；编码沿用原全局命名空间。
    return ApprovalFlow.objects.select_for_update().filter(code=flow.code).order_by('revision').first()


def new_revision(flow, actor):
    lock_series(flow)
    flow.refresh_from_db()
    if flow.status == 'draft':
        raise ValidationError('请先发布或归档当前草稿')
    if ApprovalFlow.objects.filter(code=flow.code, status='draft').exists():
        raise APIError('该流程已有草稿，请继续编辑现有草稿', status_code=409)
    number = ApprovalFlow.objects.filter(code=flow.code).aggregate(value=Max('revision'))['value'] + 1
    return ApprovalFlow.objects.create(name=flow.name, code=flow.code, revision=number,
        definition=deepcopy(flow.definition), created_by=actor, tenant_id=flow.tenant_id)


def check_workflow_version(application, data):
    expected = data.get('expected_workflow_version')
    if expected is None and application.return_count:
        raise ValidationError('退回后的流程操作必须提供当前流程版本')
    if expected is not None and expected != application.workflow_version:
        raise APIError('审批流程已变化，请刷新后重试', status_code=409)


def returnable_nodes(application, steps):
    if not application.flow_id or application.status != 'pending' or application.return_count >= 100:
        return []
    rows = list(steps)
    current = max((step.sequence for step in rows if step.status == 'pending'), default=-1)
    visits = defaultdict(list)
    for step in rows:
        if step.sequence < current and step.node_key != application.current_node:
            visits[(step.sequence, step.node_key)].append(step.status)
    result = []
    for (_, key), statuses in sorted(visits.items(), reverse=True):
        if key not in result and 'approved' in statuses and all(status in {'approved', 'skipped'} for status in statuses):
            result.append(key)
    return result
