"""
自定义异常处理
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.exceptions import APIException
from django.db.models.deletion import ProtectedError
from django.db import DatabaseError
import logging

logger = logging.getLogger(__name__)


class APIError(APIException):
    """API 异常基类"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = '请求出错'
    default_code = 'error'

    def __init__(self, detail=None, code=None, status_code=None):
        if detail:
            self.detail = detail
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class ValidationError(APIError):
    """验证错误"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = '参数验证失败'


class AuthenticationError(APIError):
    """认证错误"""
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = '认证失败'


class PermissionError(APIError):
    """权限错误"""
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = '没有权限访问'


class NotFoundError(APIError):
    """资源不存在"""
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = '资源不存在'


def custom_exception_handler(exc, context):
    """自定义异常处理器

    统一响应格式：{code, message, data}
    - 标准 DRF 异常（ValidationError/NotAuthenticated/PermissionDenied/Http404 等）
      保留原始状态码，详细信息放入 data
    - 未捕获异常记录日志并返回 500
    """
    from rest_framework.views import exception_handler as drf_exception_handler

    if isinstance(exc, DatabaseError):
        from config import db_router
        if db_router.should_fallback():
            response = Response({'code': 503, 'message': '只读服务暂不可用', 'data': None}, status=503)
            response._admincore_replica_failure = True
            return response

    if isinstance(exc, ProtectedError):
        return Response({'code': 409, 'message': '该记录仍被业务数据引用，请先处理关联记录', 'data': None},
                        status=status.HTTP_409_CONFLICT)

    response = drf_exception_handler(exc, context)
    if response is not None:
        detail = getattr(exc, 'detail', response.data)
        # detail 可能是字符串、字典或列表；简单字符串直接作为 message
        if isinstance(detail, (str,)):
            message, error_data = detail, None
        else:
            message = {
                400: '参数验证失败',
                401: '认证失败',
                403: '没有权限访问',
                404: '资源不存在',
                405: '请求方法不允许',
                429: '请求过于频繁',
            }.get(response.status_code, '请求出错')
            error_data = response.data
        response.data = {
            'code': response.status_code,
            'message': message,
            'data': error_data,
        }
        return response

    # 处理其他异常
    request = context.get('request')
    logger.error('Unhandled API exception', extra={'event': 'http.exception',
        'request_id': getattr(request, 'request_id', ''), 'exception_type': type(exc).__name__},
        exc_info=(type(exc), exc, exc.__traceback__))
    return Response({
        'code': 500,
        'message': '服务器内部错误',
        'data': None,
        'request_id': getattr(request, 'request_id', ''),
    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
