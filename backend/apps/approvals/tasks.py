"""有界扫描超时待办；与决策共用申请锁，事务内记录通知和处理结果。"""
from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.events import enqueue_event
from apps.core.modules import require_task
from apps.core.tenancy import enabled, tenant_context
from .models import ApprovalAction, ApprovalRequest, ApprovalStep


def available_user(identifier, application):
    users = get_user_model().objects.filter(pk=identifier, is_active=True, is_service_account=False)
    if enabled():
        if not application.tenant_id:
            return None
        users = users.filter(tenant_memberships__tenant_id=application.tenant_id,
            tenant_memberships__is_active=True, tenant_memberships__tenant__status='active')
    return users.first()


@shared_task(name='approvals.scan_overdue', soft_time_limit=50, time_limit=60)
def scan_overdue(limit=100):
    require_task('approvals.scan_overdue')
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('扫描批量范围为1至1000')
    now = timezone.now()
    due = Q(due_at__lte=now, reminded_at__isnull=True) | Q(escalate_at__lte=now, escalated_at__isnull=True)
    rows = ApprovalStep.all_objects.filter(due, status='pending', request__status='pending')
    if enabled():
        rows = rows.filter(tenant__status='active')
    processed, unavailable = 0, 0
    for identifier, application_id, tenant_id in rows.order_by('due_at', 'pk').values_list('pk', 'request_id', 'tenant_id')[:limit]:
        with tenant_context(tenant_id), transaction.atomic():
            applications = ApprovalRequest.objects.select_for_update(skip_locked=True) if connection.features.has_select_for_update_skip_locked else ApprovalRequest.objects.select_for_update()
            application = applications.filter(pk=application_id, status='pending').first()
            if application is None:
                continue
            step = ApprovalStep.objects.select_for_update().filter(due, pk=identifier, status='pending', node_key=application.current_node).first()
            if step is None:
                continue
            for action, deadline, stamp, recipient in [
                ('remind', step.due_at, 'reminded_at', step.delegated_to_id or step.assignee_id),
                ('escalate', step.escalate_at, 'escalated_at', step.escalation_user_id),
            ]:
                if deadline is None or deadline > now or getattr(step, stamp) is not None:
                    continue
                user = available_user(recipient, application)
                outcome = 'queued' if user else 'unavailable'
                if user:
                    enqueue_event('notification.created', f'approval:{application.pk}:step:{step.pk}:{action}', {
                        'recipient_ids': [str(user.pk)],
                        'title': '审批待办已超时' if action == 'remind' else '审批超时升级，请关注',
                        'content': '', 'notification_type': 'approval', 'link': '/approvals',
                        'data': {'request_id': str(application.pk), 'step_id': str(step.pk)},
                    })
                else:
                    errors = set(filter(None, step.timeout_error.split(',')))
                    errors.add(action)
                    step.timeout_error = ','.join(sorted(errors))
                    unavailable += 1
                ApprovalAction.objects.create(request=application, step=step, action=action, actor=None,
                    target_user=user, metadata={'system': True, 'outcome': outcome, 'sequence': step.sequence,
                        'deadline': deadline.isoformat()})
                setattr(step, stamp, now)
                processed += 1
            step.save(update_fields=['reminded_at', 'escalated_at', 'timeout_error', 'updated_at'])
    return {'processed': processed, 'unavailable': unavailable}
