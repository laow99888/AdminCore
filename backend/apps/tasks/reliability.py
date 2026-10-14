"""登记策略、可靠失败告警和不可自动重放的失联语义。"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.core.events import enqueue_event
from apps.core.modules import module_enabled
from apps.core.system_config import config_value
from apps.permissions.permissions import has_permission_code


def policy(kind):
    if kind not in ('import', 'maintenance'):
        raise ValueError('unregistered_task_policy')
    soft = config_value('tasks.' + kind + '_timeout')
    return {'soft_timeout': soft, 'hard_timeout': soft + 30,
            'dispatch_attempts': config_value('tasks.dispatch_attempts'),
            'automatic_execution_retries': 0, 'queue_expiry': 86400}


def authorize(request, code):
    """调用者在 atomic 中：用户 → 会话 → 批次 → 任务。"""
    actor = get_user_model().objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
    if actor is None:
        raise AuthenticationFailed('登录凭据已撤销')
    if request.auth is not None:
        from apps.auth_app.sessions import locked_request_session
        locked_request_session(request, actor)
    if actor.must_change_password or not has_permission_code(actor, code):
        raise PermissionDenied('没有任务操作权限或需要修改初始密码')
    return actor


def valid_execution(execution, actor):
    if (actor is None or not actor.is_active or actor.must_change_password
            or actor.session_version != execution.session_version):
        return False
    if execution.session_id:
        from apps.auth_app.sessions import active_sessions
        return active_sessions().filter(pk=execution.session_id, user=actor).exists()
    return True  # 旧请求/终端测试仅有版本；新 JWT 提交必须绑定设备。


def failure_event(record):
    if (not module_enabled('tasks') or not config_value('tasks.failure_alert')
            or (record.related_resource == 'maintenance:backup' and not config_value('tasks.failure_email'))):
        return
    event = enqueue_event('task.failed', 'task-failed:' + str(record.pk), {'record_id': str(record.pk)})
    from .models import ImportExecution, MaintenanceRequest
    origin = (ImportExecution.objects.filter(pk=record.pk).values_list('request_id', flat=True).first()
              or MaintenanceRequest.objects.filter(pk=record.pk).values_list('request_id', flat=True).first())
    if origin:
        type(event).objects.filter(pk=event.pk).update(request_id=origin)


@transaction.atomic
def deliver_failure(payload):
    """只投递仍有任务读取范围的当前身份；不将正文/联系方式带入事件。"""
    from .models import TaskRecord
    from apps.core.data_scope import scope_queryset
    from apps.notifications.models import Notification
    record = TaskRecord.objects.filter(pk=payload.get('record_id'), status='failed').first()
    if not record or not module_enabled('tasks') or not module_enabled('notifications'):
        return
    users = get_user_model().objects.select_for_update().filter(is_active=True).filter(
        Q(pk=record.creator_id) | Q(is_staff=True) | Q(is_superuser=True)).order_by('pk')[:100]
    recipients = [user for user in users if not user.must_change_password
                  and has_permission_code(user, 'task:read')
                  and scope_queryset(TaskRecord.objects.filter(pk=record.pk), user, 'task', 'creator_id').exists()]
    if not recipients:
        return
    if record.related_resource != 'maintenance:backup':
        Notification.push([user.pk for user in recipients], '任务执行失败',
            content='请在任务中心检查失败原因；已提交的数据保留，未知结果不会自动重放。',
            notification_type='task', link='/tasks', data={'record_id': str(record.pk)},
            dedupe_key='task-failed:' + str(record.pk))
    from apps.notifications.message_channels import enabled
    if config_value('tasks.failure_email') and enabled('email'):
        addresses = [user.email for user in recipients if user.email_verified and user.email
                     and user.verified_email.strip().lower() == user.email.strip().lower()]
        if addresses:
            from django.core.mail import EmailMessage
            from django.conf import settings
            message = EmailMessage('AdminCore 任务执行失败',
                '任务编号：' + str(record.pk) + '\n请登录任务中心检查。邮件不包含业务数据或原始错误。',
                settings.DEFAULT_FROM_EMAIL, bcc=addresses,
                headers={'Message-ID': '<task-failed-' + str(record.pk) + '@admincore.local>'})
            if message.send(fail_silently=False) != 1:
                raise RuntimeError('task_alert_email_failed')


def recover_lost_imports(limit=100):
    """只有 SQL 原子行提交可接续；不自动重放未知副作用。"""
    if not module_enabled('data_io'):
        return
    from .models import ImportExecution, ImportBatch, TaskRecord
    rows = list(ImportExecution.objects.filter(record__status__in=['pending', 'running'])
                .select_related('record').order_by('record__created_at')[:limit])
    for execution in rows:
        record = execution.record
        current = execution.policy or policy('import')
        now = timezone.now()
        due = (record.created_at < now - timedelta(seconds=current['queue_expiry']) if record.status == 'pending'
               else record.started_at is not None and record.started_at < now - timedelta(seconds=current['hard_timeout'] + 60))
        if due:
            with transaction.atomic():
                # worker 同顺序；正在提交的一行先完成，后续行检测失败即停止。
                ImportBatch.objects.select_for_update().get(pk=execution.batch_id)
                locked = TaskRecord.objects.select_for_update().get(pk=record.pk)
                if locked.status == record.status:
                    locked.mark_failed('queue_expired' if locked.status == 'pending' else 'worker_lost_committed_rows_preserved')
