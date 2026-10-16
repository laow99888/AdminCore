"""持久领取外部副作用；网络 I/O 不持有事件或用户数据库锁。"""
from datetime import timedelta
from uuid import UUID
import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import OutboxEvent
from apps.logs.context import correlated_request

TOPICS = ('notification.delivery', 'task.failed', 'auth.email', 'file.purge')
LEASE_SECONDS = 300
logger = logging.getLogger(__name__)


def dispatch_external(limit):
    now = timezone.now()
    eligible = (Q(status__in=('pending', 'failed')) | Q(status='processing')) & Q(available_at__lte=now)
    rows = list(OutboxEvent.objects.filter(eligible, topic__in=TOPICS)
        .exclude(last_error='dispatch_exhausted').order_by('created_at').values_list('pk', flat=True)[:limit])
    processed = failed = 0
    for identifier in rows:
        with transaction.atomic():
            event = OutboxEvent.objects.select_for_update().filter(eligible, pk=identifier).first()
            if event is None or event.last_error == 'dispatch_exhausted':
                continue
            uncertain_delivery = False
            if event.topic == 'notification.delivery':
                from apps.notifications.models import MessageDelivery
                try:
                    delivery_id = UUID(str(event.payload['delivery_id']))
                except (ValueError, KeyError, TypeError):
                    event.status, event.last_error = 'failed', 'dispatch_exhausted'
                    event.save(update_fields=['status', 'last_error', 'updated_at'])
                    failed += 1
                    continue
                delivery_status = MessageDelivery.objects.filter(pk=delivery_id).values_list('status', flat=True).first()
                if delivery_status in ('succeeded', 'terminated'):
                    # 渠道结果已持久化，仅事件写回中断；不把已确认结果改判为未知。
                    event.status, event.last_error, event.published_at = 'succeeded', '', timezone.now()
                    event.save(update_fields=['status', 'last_error', 'published_at', 'updated_at'])
                    processed += 1
                    continue
                uncertain_delivery = delivery_status == 'sending'
            if event.topic == 'notification.delivery' and (event.status == 'processing' or uncertain_delivery):
                # 不可确定是否已经送达的消息禁止自动重放，迟到 worker 也不能覆盖终止状态。
                from apps.notifications.models import MessageDelivery
                MessageDelivery.objects.filter(pk=delivery_id,
                    status__in=('pending', 'failed', 'sending')).update(
                    status='terminated', last_error='delivery_outcome_unknown')
                event.status, event.last_error = 'failed', 'dispatch_exhausted'
                event.save(update_fields=['status', 'last_error', 'updated_at'])
                failed += 1
                continue
            if event.topic != 'file.purge' and event.attempts >= 5:
                event.status, event.last_error = 'failed', 'dispatch_exhausted'
                event.save(update_fields=['status', 'last_error', 'updated_at'])
                continue
            event.attempts += 1
            event.status, event.available_at = 'processing', now + timedelta(seconds=LEASE_SECONDS)
            event.save(update_fields=['status', 'attempts', 'available_at', 'updated_at'])
        error = ''
        with correlated_request(event.request_id):
            try:
                if event.topic == 'notification.delivery':
                    from apps.notifications.message_services import deliver
                    if deliver(event.payload):
                        error = 'channel_delivery_failed'
                elif event.topic == 'task.failed':
                    from apps.tasks.reliability import deliver_failure
                    deliver_failure(event.payload)
                elif event.topic == 'auth.email':
                    from apps.auth_app.recovery import deliver_challenge
                    deliver_challenge(event.payload)
                else:
                    from apps.files.deletion import purge_object
                    purge_object(event.payload)
            except Exception as exc:
                # 外部异常正文可含地址、签名和业务内容，禁止持久化。
                error = type(exc).__name__
        values = {'status': 'failed' if error else 'succeeded', 'last_error': error,
                  'available_at': timezone.now() + timedelta(seconds=min(3600, 2 ** min(event.attempts, 12))),
                  'published_at': None if error else timezone.now(), 'updated_at': timezone.now()}
        # attempts 是单调递增的领取代数；迟到的旧领取不能回写新状态。
        updated = OutboxEvent.objects.filter(pk=event.pk, status='processing', attempts=event.attempts).update(**values)
        if updated:
            with correlated_request(event.request_id):
                logger.log(logging.WARNING if error else logging.INFO, 'Reliable external event processed',
                    extra={'event': 'outbox.failed' if error else 'outbox.succeeded', 'event_id': str(event.pk)})
        processed += int(bool(updated) and not error)
        failed += int(bool(updated) and bool(error))
    return {'processed': processed, 'failed': failed}
