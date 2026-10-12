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

    def get_paginated_response(self, data):
        return Response({
            'code': 200,
            'message': 'success',
            'data': {
                'items': data,
                'pagination': {
                    'total': self.page.paginator.count,
                    'page': self.page.number,
                    'page_size': self.page_size,
                    'total_pages': self.page.paginator.num_pages,
                }
            }
        })
