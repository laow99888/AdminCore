"""
自定义中间件
"""

import uuid
import json
import logging
import time
from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)


class PasswordChangeSessionMiddleware(MiddlewareMixin):
    """同时保护 Django 管理后台的会话认证，避免绕过 JWT 限制。"""
    def process_view(self, request, view_func, view_args, view_kwargs):
        if (request.user.is_authenticated and request.resolver_match.namespace == 'admin'
                and request.resolver_match.view_name != 'admin:logout'):
            from apps.auth_app.models import TOTPDevice
            if TOTPDevice.objects.filter(user=request.user).exclude(active_secret='').exists():
                return JsonResponse({'code': 403, 'message': '已启用双因素认证，请使用系统登录入口',
                                     'data': {'reason': 'mfa_required'}}, status=403)
        if (request.user.is_authenticated and request.user.must_change_password
                and request.resolver_match.view_name != 'admin:logout'):
            return JsonResponse({'code': 403, 'message': '请通过系统登录页修改初始密码',
                                 'data': {'reason': 'password_change_required'}}, status=403)


class RequestTrackingMiddleware:
    """请求追踪中间件 - 为每个请求添加唯一 ID"""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def prepare(self, request):
        # 生成请求追踪 ID
        request.request_id = str(uuid.uuid4())
        # 可选：从请求头获取或生成
        incoming = request.headers.get('X-Request-ID', '')
        if 0 < len(incoming) <= 100 and all(char.isascii() and (char.isalnum() or char in '-_.') for char in incoming):
            request.request_id = incoming
        from apps.logs.context import request_id
        request._tracking_started = time.monotonic()
        return request_id.set(request.request_id)

    def finish(self, request, response):
        response['X-Request-ID'] = request.request_id
        logger.info('HTTP request completed', extra={'event': 'http.completed',
            'status_code': response.status_code,
            'duration_ms': (time.monotonic() - request._tracking_started) * 1000})
        return response

    def __call__(self, request):
        if self.is_async:
            return self.async_call(request)
        from apps.logs.context import request_id
        token = self.prepare(request)
        try:
            response = self.get_response(request)
            return self.finish(request, response)
        finally:
            request_id.reset(token)
            from apps.core.tenancy import clear_current_tenant
            clear_current_tenant()

    async def async_call(self, request):
        from apps.logs.context import request_id
        token = self.prepare(request)
        try:
            response = await self.get_response(request)
            return self.finish(request, response)
        finally:
            request_id.reset(token)
            from apps.core.tenancy import clear_current_tenant
            clear_current_tenant()


class ErrorHandlingMiddleware(MiddlewareMixin):
    """错误处理中间件 - 捕获未处理的异常"""

    def process_exception(self, request, exception):
        if isinstance(exception, PermissionDenied):
            # Django 已有 403 处理器；权限拒绝不是未处理的服务器错误。
            return None
        logger.error(
            'Unhandled request exception',
            extra={
                'event': 'http.exception',
                'request_id': getattr(request, 'request_id', ''),
                'exception_type': type(exception).__name__,
            },
            exc_info=(type(exception), exception, exception.__traceback__),
        )

        return JsonResponse({
            'code': 500,
            'message': '服务器内部错误',
            'data': None,
            'request_id': getattr(request, 'request_id', ''),
        }, status=500)
