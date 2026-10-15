"""
分页类
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """标准分页"""
    page_size = 10
    page_size_query_param = 'page_size'
    page_size_query_description = '每页条数'
    max_page_size = 100

    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object', 'required': ['code', 'message', 'data'],
            'properties': {
                'code': {'type': 'integer'}, 'message': {'type': 'string'},
                'data': {'type': 'object', 'required': ['items', 'pagination'], 'properties': {
                    'items': schema,
                    'pagination': {'type': 'object', 'properties': {
                        key: {'type': 'integer'} for key in ['total', 'page', 'page_size', 'total_pages']
                    }},
                }},
            },
        }

    def get_paginated_response(self, data):
        return Response({
            'code': 200,
            'message': 'success',
            'data': {
                'items': data,
                'pagination': {
                    'total': self.page.paginator.count,
                    'page': self.page.number,
                    'page_size': self.page.paginator.per_page,
                    'total_pages': self.page.paginator.num_pages,
                }
            }
        })
