"""仅保存关联 ID；不把请求体、头、Cookie 或认证凭据放进上下文。"""
from contextvars import ContextVar

request_id = ContextVar('audit_request_id', default='')
