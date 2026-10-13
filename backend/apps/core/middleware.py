"""
自定义中间件
"""

import uuid
import json
import logging
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse

logger = logging.getLogger(__name__)


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
