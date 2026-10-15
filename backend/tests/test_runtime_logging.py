"""真实日志格式、Celery 信号和 outbox 关联，不序列化凭据或正文。"""
import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.core.runtime_logging import SafeJSONFormatter
from apps.logs.context import correlated_request, request_id, task_id
from config.celery import begin_task_context, end_task_context


def test_formatter_never_renders_raw_arguments_exceptions_or_extra_payload():
    record = logging.LogRecord('fixture', logging.ERROR, '/private/source.py', 42,
        'password=%s https://secret@internal?token=leaked', ('super-secret',), None)
    record.event = 'http.exception'
    record.payload = {'cookie': 'secret-cookie'}
    try:
        raise ValueError('sensitive-exception-message')
    except ValueError:
        import sys
        record.exc_info = sys.exc_info()
    with correlated_request('http-safe-123'):
        row = json.loads(SafeJSONFormatter().format(record))
    assert row['event'] == 'http.exception' and row['request_id'] == 'http-safe-123'
    assert row['exception_type'] == 'ValueError' and row['source'] == 'source.py:42'
    assert not any(secret in str(row) for secret in ('super-secret', 'secret@', 'leaked', 'secret-cookie', '/private/', 'sensitive-exception'))


def test_formatter_rejects_unsafe_ids_and_unknown_events():
    record = logging.makeLogRecord({'name': 'fixture', 'event': 'secret-unknown-event',
        'request_id': 'bad\nsecret', 'task_id': 'https://private', 'delivery_id': 'valid-id-123',
        'duration_ms': float('nan'), 'status_code': 200})
    row = json.loads(SafeJSONFormatter().format(record))
    assert row['event'] == 'runtime.log' and row['request_id'] == row['task_id'] == ''
    assert row['delivery_id'] == 'valid-id-123' and 'duration_ms' not in row


def test_task_signal_context_restores_outer_request_and_clears_next_task():
    task = SimpleNamespace(request=SimpleNamespace(headers={'request_id': 'http-origin-456'}))
    with correlated_request('outer-request'):
        begin_task_context(task_id='celery-task-123', task=task)
        assert request_id.get() == 'http-origin-456' and task_id.get() == 'celery-task-123'
        end_task_context(task=task)
        assert request_id.get() == 'outer-request' and task_id.get() == ''
        task.request.headers = {'request_id': 'invalid\nsecret'}
        begin_task_context(task_id='next-task', task=task)
        assert request_id.get() == ''
        end_task_context(task=task)
    assert request_id.get() == task_id.get() == ''


@pytest.mark.django_db
def test_outbox_restores_each_event_context_and_propagates_worker_header(admin_user, caplog):
    from django.utils import timezone
    from apps.core.events import enqueue_event
    from apps.core.models import OutboxEvent
    from apps.core.tasks import dispatch_outbox
    from apps.tasks.models import TaskRecord, MaintenanceRequest
    from apps.tasks.reliability import policy
    record = TaskRecord.objects.create(name='correlated', creator=admin_user)
    MaintenanceRequest.objects.create(record=record, key='lifecycle', session_version=1,
        request_id='origin-http-task', policy=policy('maintenance'))
    OutboxEvent.objects.create(topic='maintenance.requested', event_key='context-maintenance',
        payload={'record_id': str(record.pk)}, request_id='origin-http-task', available_at=timezone.now())
    OutboxEvent.objects.create(topic='notification.created', event_key='context-notification',
        payload={'recipient_ids': [str(admin_user.pk)], 'title': 'private-message'},
        request_id='origin-http-message', available_at=timezone.now())
    caplog.set_level(logging.INFO, logger='apps.core.tasks')
    observed = []
    def capture(record):
        if getattr(record, 'event', '').startswith('outbox.'):
            observed.append(json.loads(SafeJSONFormatter().format(record)))
    with patch('apps.tasks.tasks.run_maintenance.apply_async') as publish, \
         patch('apps.core.tasks.logger.log', side_effect=lambda level, message, extra: capture(logging.makeLogRecord({'levelno': level, 'msg': message, **extra}))):
        with correlated_request('outer-context'):
            assert dispatch_outbox() == {'processed': 2, 'failed': 0}
            assert request_id.get() == 'outer-context'
        assert publish.call_args.kwargs['headers'] == {'request_id': 'origin-http-task'}
    assert {row['request_id'] for row in observed} == {'origin-http-task', 'origin-http-message'}
    from apps.tasks.serializers import TaskRecordSerializer
    assert TaskRecordSerializer(record).data['request_id'] == 'origin-http-task'
    with correlated_request('inherited-context'):
        event = enqueue_event('fixture', 'inherited-context-event', {})
    assert event.request_id == 'inherited-context'
