"""
日志查看视图
"""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import OperationLog, LoginLog, ExceptionLog
from .serializers import OperationLogSerializer, OperationLogListSerializer, LoginLogSerializer, ExceptionLogSerializer
from apps.permissions.permissions import HasPermission
from apps.core.data_scope import scope_queryset
from apps.core.query_budget import QueryBudgetListMixin


class ScopedLogViewSet(QueryBudgetListMixin, viewsets.ReadOnlyModelViewSet):
    ordering_fields = ['created_at']

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    def get_queryset(self):
        return scope_queryset(super().get_queryset(), self.request.user, 'log', 'user_id')


class OperationLogViewSet(ScopedLogViewSet):
    """操作日志查看"""
    queryset = OperationLog.objects.select_related('user').all()
    serializer_class = OperationLogSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'log:read'
    filterset_fields = ['action', 'resource', 'user', 'request_id', 'task_id', 'task_record_id']
    search_fields = ['description', 'user__username']
    ordering = ['-created_at']

    def get_serializer_class(self):
        return OperationLogListSerializer if self.action == 'list' else OperationLogSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.defer('before_values', 'after_values', 'batch_results') if self.action == 'list' else queryset


class LoginLogViewSet(ScopedLogViewSet):
    """登录日志查看"""
    queryset = LoginLog.objects.all()
    serializer_class = LoginLogSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'log:read'
    filterset_fields = ['status', 'username']
    search_fields = ['username']
    ordering = ['-created_at']


class ExceptionLogViewSet(ScopedLogViewSet):
    """异常日志查看"""
    queryset = ExceptionLog.objects.select_related('user').all()
    serializer_class = ExceptionLogSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'log:read'
    filterset_fields = ['level', 'request_method']
    search_fields = ['message', 'request_path']
    ordering = ['-created_at']
