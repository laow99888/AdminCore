"""
自定义中间件
"""

import uuid
import json
import logging
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse

logger = logging.getLogger(__name__)


class PasswordChangeSessionMiddleware(MiddlewareMixin):
    """同时保护 Django 管理后台的会话认证，避免绕过 JWT 限制。"""
    def process_view(self, request, view_func, view_args, view_kwargs):
        if (request.user.is_authenticated and request.user.must_change_password
                and request.resolver_match.view_name != 'admin:logout'):
            return JsonResponse({'code': 403, 'message': '请通过系统登录页修改初始密码',
                                 'data': {'reason': 'password_change_required'}}, status=403)


class RequestTrackingMiddleware(MiddlewareMixin):
    """请求追踪中间件 - 为每个请求添加唯一 ID"""

    def process_request(self, request):
        # 生成请求追踪 ID
        request.request_id = str(uuid.uuid4())
        # 可选：从请求头获取或生成
        incoming = request.headers.get('X-Request-ID', '')
        if 0 < len(incoming) <= 100 and all(char.isascii() and (char.isalnum() or char in '-_.') for char in incoming):
            request.request_id = incoming
        return None

    def process_response(self, request, response):
        # 在响应头中添加请求 ID
        response['X-Request-ID'] = getattr(request, 'request_id', '')
        return response


class ErrorHandlingMiddleware(MiddlewareMixin):
    """错误处理中间件 - 捕获未处理的异常"""

    def process_exception(self, request, exception):
        logger.error(
            f'Exception: {str(exception)}',
            extra={
                'request_id': getattr(request, 'request_id', ''),
                'method': request.method,
                'path': request.path,
            },
            exc_info=True
        )

        return JsonResponse({
            'code': 500,
            'message': '服务器内部错误',
            'data': None,
            'request_id': getattr(request, 'request_id', ''),
        }, status=500)
