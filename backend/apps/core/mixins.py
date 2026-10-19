"""
统一响应包 Mixin
"""

from rest_framework.response import Response
from .query_budget import QueryBudgetListMixin

SUCCESS_MESSAGES = {
    'create': '创建成功',
    'update': '更新成功',
    'partial_update': '更新成功',
    'retrieve': 'success',
}


class PrivateResponseMixin:
    """敏感接口统一禁止共享缓存；保留状态码、Cookie 和内容协商结果。"""
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response


class EnvelopeResponseMixin(QueryBudgetListMixin):
    """把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}

    list 已由 StandardPagination.get_paginated_response 统一包装；
    自定义 action 自行构造 Response 的不受影响。
    """

    def create(self, request, *args, **kwargs):
        return self._envelope(super().create(request, *args, **kwargs))

    def update(self, request, *args, **kwargs):
        # 注意不要同时覆写 partial_update：DRF 的 partial_update 内部委托 self.update，
        # 两边都包会导致双重 {code,message,data}
        return self._envelope(super().update(request, *args, **kwargs))

    def retrieve(self, request, *args, **kwargs):
        return self._envelope(super().retrieve(request, *args, **kwargs))

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({'code': 200, 'message': '删除成功', 'data': None})

    def _envelope(self, response):
        message = SUCCESS_MESSAGES.get(getattr(self, 'action', ''), 'success')
        # 原响应保留状态、Location/ETag/Retry-After、Cookie 和 renderer 元信息。
        # 响应体变更后不能沿用旧长度，Content-Type 由最终渲染器决定。
        response.data = {'code': 200, 'message': message, 'data': response.data}
        if response.has_header('Content-Length'):
            del response['Content-Length']
        return response
