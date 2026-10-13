"""事务内可靠事件记录与事务提交后的派发触发。"""
import logging
from django.db import transaction
from django.utils import timezone

from .models import OutboxEvent
logger = logging.getLogger(__name__)


def enqueue_event(topic, event_key, payload, request=None):
    with transaction.atomic():
        event, created = OutboxEvent.objects.get_or_create(
            event_key=event_key,
            defaults={'topic': topic, 'payload': payload, 'available_at': timezone.now(),
                      'request_id': str(getattr(request, 'request_id', ''))[:100]},
        )
        if not created and (event.topic != topic or event.payload != payload):
            raise ValueError('事件键已用于另一份事件')
        transaction.on_commit(_dispatch_after_commit)
    return event


def _dispatch_after_commit():
    try:
        from .tasks import dispatch_outbox
        dispatch_outbox.delay()
    except Exception:
        logger.warning('可靠事件触发未成功；等待定时补偿派发')
