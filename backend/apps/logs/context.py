"""仅保存关联 ID；不把请求体、头、Cookie 或认证凭据放进上下文。"""
from contextvars import ContextVar
from contextlib import contextmanager

request_id = ContextVar('audit_request_id', default='')
task_id = ContextVar('runtime_task_id', default='')


def correlation_id(value):
    """Accept the same opaque safe identifier grammar as HTTP tracking."""
    return value if (isinstance(value, str) and 0 < len(value) <= 100
                     and all(char.isascii() and (char.isalnum() or char in '-_.') for char in value)) else ''


@contextmanager
def correlated_request(value):
    token = request_id.set(correlation_id(value))
    try:
        yield
    finally:
        request_id.reset(token)
