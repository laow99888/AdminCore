"""持久领取外部副作用；网络 I/O 不持有事件或用户数据库锁。"""
from datetime import timedelta
from uuid import UUID
import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import OutboxEvent
from .tenancy import tenant_context
from apps.logs.context import correlated_request
from . import broker_dispatch

TOPICS = ('notification.delivery', 'task.failed', 'auth.email', 'file.purge', *broker_dispatch.TOPICS)
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
            attempt_limit = 5
            if event.topic in broker_dispatch.TOPICS:
                with tenant_context(event.tenant_id):
                    execution = broker_dispatch.execution_for(event)
                    attempt_limit = broker_dispatch.dispatch_policy(event, execution)['dispatch_attempts']
                    if execution and execution.record.status == 'pending' and event.attempts >= attempt_limit:
                        execution.record.mark_failed('dispatch_attempts_exhausted')
            if event.topic != 'file.purge' and event.attempts >= attempt_limit:
                event.status, event.last_error = 'failed', 'dispatch_exhausted'
                event.save(update_fields=['status', 'last_error', 'updated_at'])
                # 已耗尽事件没有再次派发，不重复计入本批失败数。
                continue
            event.attempts += 1
            event.status, event.available_at = 'processing', now + timedelta(seconds=LEASE_SECONDS)
            event.save(update_fields=['status', 'attempts', 'available_at', 'updated_at'])
        error = ''
        deferred_until = None
        with correlated_request(event.request_id), tenant_context(event.tenant_id):
            try:
                if event.topic in broker_dispatch.TOPICS:
                    broker_dispatch.publish(event)
                elif event.topic == 'notification.delivery':
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
                if event.topic == 'notification.delivery':
                    from apps.notifications.preferences import DeliveryDeferred
                    if isinstance(exc, DeliveryDeferred):
                        deferred_until = exc.until
                    else:
                        error = type(exc).__name__
                else:
                    error = type(exc).__name__
                # 外部异常正文可含地址、签名和业务内容，禁止持久化。
        if deferred_until is not None:
            # 免打扰尚未发送，不消耗失败重试；租约时间同时作为领取标识，
            # 防止归还attempt之后迟到旧worker覆盖下一次同attempt的领取。
            OutboxEvent.objects.filter(pk=event.pk, status='processing', attempts=event.attempts,
                available_at=event.available_at).update(status='pending', available_at=deferred_until,
                    attempts=event.attempts - 1, last_error='', updated_at=timezone.now())
            continue
        values = {'status': 'failed' if error else 'succeeded', 'last_error': error,
                  'available_at': timezone.now() + (timedelta(seconds=min(3600, 2 ** min(event.attempts, 12))) if error else timedelta()),
                  'published_at': None if error else timezone.now(), 'updated_at': timezone.now()}
        # attempt与租约共同匹配，迟到的旧领取不能回写新状态。
        updated = OutboxEvent.objects.filter(pk=event.pk, status='processing', attempts=event.attempts,
                                            available_at=event.available_at).update(**values)
        if updated:
            with correlated_request(event.request_id):
                logger.log(logging.WARNING if error else logging.INFO, 'Reliable external event processed',
                    extra={'event': 'outbox.failed' if error else 'outbox.succeeded', 'event_id': str(event.pk),
                           'record_id': str(event.payload.get('record_id', '')),
                           'delivery_id': str(event.payload.get('delivery_id', ''))})
        processed += int(bool(updated) and not error)
        failed += int(bool(updated) and bool(error))
    return {'processed': processed, 'failed': failed}
