"""Structured runtime logs with explicit fields, without payloads or exception text."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from apps.logs.context import correlation_id, request_id, task_id


class SafeJSONFormatter(logging.Formatter):
    """Never interpolate arbitrary log arguments, HTTP data or exception messages.

    Unregistered third-party messages retain severity and source location.
    Detailed business changes live in the separate permission-protected audit.
    """
    EVENTS = {'http.exception', 'http.completed', 'task.started', 'task.finished',
              'outbox.succeeded', 'outbox.failed', 'file.scan', 'file.scan_audit_failed'}
    IDENTIFIERS = ('event_id', 'record_id', 'delivery_id')
    MESSAGES = {
        'Cleanup soft deleted files failed', 'Cleanup expired notifications failed', '批量用户操作失败',
        '可靠事件触发未成功；等待定时补偿派发', '暂存头像清理失败，保留记录 %s',
        'Import execution failed: record=%s error=%s', 'Cleanup purged %d expired files',
        'Revoke celery task %s failed: %s', 'Celery broker 不可用（%s），任务改为同步执行',
    }

    def format(self, record):
        event = getattr(record, 'event', '')
        row = {'timestamp': datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
               'level': record.levelname, 'logger': str(record.name or '')[:200],
               'event': event if event in self.EVENTS else 'runtime.log',
               'request_id': correlation_id(getattr(record, 'request_id', '') or request_id.get()),
               'task_id': correlation_id(getattr(record, 'task_id', '') or task_id.get()),
               'source': f'{Path(record.pathname).name}:{record.lineno}'}
        if isinstance(record.msg, str) and record.msg in self.MESSAGES:
            row['message_template'] = record.msg
        for field in self.IDENTIFIERS:
            value = correlation_id(getattr(record, field, ''))
            if value:
                row[field] = value
        for field in ('status_code', 'duration_ms'):
            value = getattr(record, field, None)
            if type(value) in (int, float) and 0 <= value <= 1e12:
                row[field] = round(value, 3)
        state = getattr(record, 'task_state', None)
        if state in ('SUCCESS', 'FAILURE', 'RETRY', 'REVOKED'):
            row['task_state'] = state
        if event == 'file.scan':
            scan_state = getattr(record, 'scan_state', '')
            if scan_state in ('clean', 'infected', 'unavailable', 'limit'):
                row['scan_state'] = scan_state
            digest = getattr(record, 'scan_sha256', '')
            if isinstance(digest, str) and len(digest) == 64 and all(value in '0123456789abcdef' for value in digest):
                row['scan_sha256'] = digest
            size = getattr(record, 'scan_bytes', None)
            if type(size) is int and 0 <= size <= 500 * 1024 * 1024 + 1:
                row['scan_bytes'] = size
        if record.exc_info and record.exc_info[0]:
            row['exception_type'] = record.exc_info[0].__name__[:100]
            frames = []
            trace = record.exc_info[2]
            while trace is not None:
                frames.append({'file': Path(trace.tb_frame.f_code.co_filename).name,
                               'line': trace.tb_lineno, 'function': trace.tb_frame.f_code.co_name})
                trace = trace.tb_next
            row['frames'] = frames[-12:]
        elif correlation_id(getattr(record, 'exception_type', '')):
            row['exception_type'] = record.exception_type
        return json.dumps(row, ensure_ascii=False, allow_nan=False)
