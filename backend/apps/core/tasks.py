"""核心可靠事件与幂等记录维护任务。"""
from datetime import timedelta
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import IdempotencyRecord, OutboxEvent
from apps.logs.context import correlated_request

logger = logging.getLogger(__name__)

@shared_task(name='core.dispatch_outbox')
def dispatch_outbox(limit=100):
    """站内通知原子消费；维护请求至少一次入队，由领取状态去重。"""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise ValueError('派发批量范围为 1-1000')
    now = timezone.now()
    from apps.core.modules import module_enabled
    from apps.tasks.backup import recover_lost
    recover_lost()
    if module_enabled('tasks'):
        from apps.tasks.tasks import recover_lost_maintenance
        recover_lost_maintenance()
        from apps.tasks.reliability import recover_lost_imports
        recover_lost_imports()
    processed = failed = 0
    from django.db.models import Q
    eligible = (~Q(topic__in=['auth.email', 'notification.delivery', 'task.failed']) | Q(attempts__lt=5)) & ~Q(last_error='dispatch_exhausted')
    for event_id, origin in list(OutboxEvent.objects.filter(eligible,
        status__in=['pending', 'failed'], available_at__lte=now,
    ).order_by('created_at').values_list('id', 'request_id')[:limit]):
        with transaction.atomic(), correlated_request(origin):
            event = OutboxEvent.objects.select_for_update().filter(eligible,
                pk=event_id, status__in=['pending', 'failed'], available_at__lte=now,
            ).first()
            if event is None:
                continue
            if event.topic in ('maintenance.requested', 'import.requested'):
                from apps.tasks.models import TaskRecord, MaintenanceRequest, ImportExecution
                from apps.tasks.reliability import policy
                model = ImportExecution if event.topic == 'import.requested' else MaintenanceRequest
                execution = model.objects.select_related('record').filter(pk=event.payload.get('record_id')).first()
                current = (execution.policy if execution else None) or policy('import' if model == ImportExecution else 'maintenance')
                if execution and execution.record.status == 'pending' and event.attempts >= current['dispatch_attempts']:
                    execution.record.mark_failed('dispatch_attempts_exhausted')
                    event.status, event.last_error = 'failed', 'dispatch_exhausted'
                    event.save(update_fields=['status', 'last_error', 'updated_at'])
                    failed += 1
                    continue
            event.attempts += 1
            delivery_failed = False
            try:
                with transaction.atomic():
                    if event.topic == 'task.failed':
                        from apps.tasks.reliability import deliver_failure
                        deliver_failure(event.payload)
                    elif event.topic == 'import.requested':
                        from apps.tasks.models import ImportExecution
                        from apps.data_io.tasks import run_data_import
                        if not module_enabled('data_io'):
                            raise ValueError('data_io_disabled')
                        request = ImportExecution.objects.select_related('record').filter(pk=event.payload.get('record_id')).first()
                        if request is None:
                            raise ValueError('import_request_missing')
                        if request.record.status == 'pending':
                            run_data_import.apply_async(args=[str(request.pk)], task_id=str(request.pk),
                                headers={'request_id': event.request_id},
                                soft_time_limit=request.policy['soft_timeout'], time_limit=request.policy['hard_timeout'])
                    elif event.topic == 'maintenance.requested':
                        from apps.tasks.models import MaintenanceRequest
                        from apps.tasks.tasks import run_maintenance
                        if not module_enabled('tasks'):
                            raise ValueError('tasks_disabled')
                        request = MaintenanceRequest.objects.filter(pk=event.payload.get('record_id')).first()
                        if request is None:
                            raise ValueError('maintenance_request_missing')
                        if request.record.status == 'pending':
                            limits = request.policy or current
                            run_maintenance.apply_async(args=[str(request.pk)], task_id=str(request.pk),
                                headers={'request_id': event.request_id},
                                soft_time_limit=limits['soft_timeout'], time_limit=limits['hard_timeout'])
                    elif event.topic == 'auth.email':
                        from apps.auth_app.recovery import deliver_challenge
                        deliver_challenge(event.payload)
                    elif event.topic == 'notification.delivery':
                        from apps.notifications.message_services import deliver
                        delivery_failed = deliver(event.payload)
                    elif event.topic != 'notification.created':
                        raise ValueError('unsupported_topic')
                    else:
                        if not module_enabled('notifications'):
                            raise ValueError('notifications_disabled')
                        from django.contrib.auth import get_user_model
                        recipients = event.payload.get('recipient_ids', [])
                        if not isinstance(recipients, list) or not recipients or not all(isinstance(item, str) for item in recipients):
                            raise ValueError('invalid_recipients')
                        if len(set(recipients)) != get_user_model().objects.filter(id__in=recipients).count():
                            raise ValueError('recipient_missing')
                        from apps.notifications.models import Notification
                        Notification.push(dedupe_key=event.event_key, **event.payload)
            except Exception as exc:
                event.status = 'failed'
                event.last_error = str(exc) if str(exc) in {'unsupported_topic', 'notifications_disabled', 'recipient_missing', 'invalid_recipients'} else type(exc).__name__
                event.available_at = timezone.now() + timedelta(seconds=min(3600, 2 ** min(event.attempts, 12)))
                failed += 1
            else:
                if delivery_failed:
                    event.status, event.last_error = 'failed', 'channel_delivery_failed'
                    event.available_at = timezone.now() + timedelta(seconds=min(3600, 2 ** min(event.attempts, 12)))
                    failed += 1
                else:
                    event.status = 'succeeded'
                    event.published_at = timezone.now()
                    event.last_error = ''
                    processed += 1
            event.save(update_fields=['status', 'attempts', 'last_error', 'available_at', 'published_at', 'updated_at'])
            logger.log(logging.WARNING if event.status == 'failed' else logging.INFO,
                'Reliable event processed', extra={'event': 'outbox.failed' if event.status == 'failed' else 'outbox.succeeded',
                    'event_id': str(event.pk), 'record_id': str(event.payload.get('record_id', '')),
                    'delivery_id': str(event.payload.get('delivery_id', ''))})
    return {'processed': processed, 'failed': failed}


@shared_task(name='core.cleanup_expired_idempotency')
def cleanup_expired_idempotency():
    cutoff = timezone.now()
    deleted, _ = IdempotencyRecord.objects.filter(expires_at__lt=cutoff, status='succeeded').delete()
    return {'deleted_records': deleted}


@shared_task(name='core.cleanup_expired_sessions')
def cleanup_expired_sessions(batch_size=1000):
    """保留至少30天后分批清理失效设备记录；从不触碰有效会话。"""
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError('清理批量范围为 1-1000')
    from django.db.models import Q
    from apps.auth_app.models import AuthSession, EmailChallenge, LoginCaptchaGuard, LoginCaptchaChallenge
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    cutoff = timezone.now() - timedelta(days=30)
    session_ids = list(AuthSession.objects.filter(
        Q(expires_at__lt=cutoff) | Q(revoked_at__lt=cutoff)
    ).order_by('expires_at', 'pk').values_list('pk', flat=True)[:batch_size])
    sessions, _ = AuthSession.objects.filter(pk__in=session_ids).delete()
    token_ids = list(OutstandingToken.objects.filter(expires_at__lt=cutoff)
                     .order_by('expires_at', 'pk').values_list('pk', flat=True)[:batch_size])
    OutstandingToken.objects.filter(pk__in=token_ids).delete()
    challenge_ids = list(EmailChallenge.objects.filter(expires_at__lt=cutoff)
                         .order_by('expires_at', 'pk').values_list('pk', flat=True)[:batch_size])
    EmailChallenge.objects.filter(pk__in=challenge_ids).delete()
    captcha_cutoff = timezone.now() - timedelta(days=1)
    captcha_ids = list(LoginCaptchaChallenge.objects.filter(expires_at__lt=captcha_cutoff)
                       .order_by('expires_at', 'pk').values_list('pk', flat=True)[:batch_size])
    LoginCaptchaChallenge.objects.filter(pk__in=captcha_ids).delete()
    guard_ids = list(LoginCaptchaGuard.objects.filter(expires_at__lt=captcha_cutoff)
                     .order_by('expires_at', 'pk').values_list('pk', flat=True)[:batch_size])
    # 领取ID后可能被并发登录重新使用；删除时再次检查保留期。
    guards_deleted, _ = LoginCaptchaGuard.objects.filter(pk__in=guard_ids, expires_at__lt=captcha_cutoff).delete()
    return {'deleted_sessions': sessions, 'deleted_refresh_records': len(token_ids),
            'deleted_email_challenges': len(challenge_ids), 'deleted_login_captchas': len(captcha_ids),
            'deleted_captcha_guards': guards_deleted}
