"""核心可靠事件与幂等记录维护任务。"""
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import IdempotencyRecord, OutboxEvent

@shared_task(name='core.dispatch_outbox')
def dispatch_outbox(limit=100):
    """站内通知与完成标记共用事务，中断会回滚，由下一轮恢复。"""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise ValueError('派发批量范围为 1-1000')
    now = timezone.now()
    processed = failed = 0
    for event_id in list(OutboxEvent.objects.filter(
        status__in=['pending', 'failed'], available_at__lte=now,
    ).order_by('created_at').values_list('id', flat=True)[:limit]):
        with transaction.atomic():
            event = OutboxEvent.objects.select_for_update().filter(
                pk=event_id, status__in=['pending', 'failed'], available_at__lte=now,
            ).first()
            if event is None:
                continue
            event.attempts += 1
            try:
                with transaction.atomic():
                    if event.topic != 'notification.created':
                        raise ValueError('unsupported_topic')
                    from apps.core.modules import module_enabled
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
                event.status = 'succeeded'
                event.published_at = timezone.now()
                event.last_error = ''
                processed += 1
            event.save(update_fields=['status', 'attempts', 'last_error', 'available_at', 'published_at', 'updated_at'])
    return {'processed': processed, 'failed': failed}


@shared_task(name='core.cleanup_expired_idempotency')
def cleanup_expired_idempotency():
    cutoff = timezone.now()
    deleted, _ = IdempotencyRecord.objects.filter(expires_at__lt=cutoff, status='succeeded').delete()
    return {'deleted_records': deleted}
