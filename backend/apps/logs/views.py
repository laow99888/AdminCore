"""
日志查看视图
"""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import OperationLog, LoginLog, ExceptionLog
from .serializers import OperationLogSerializer, LoginLogSerializer, ExceptionLogSerializer
from apps.permissions.permissions import HasPermission
from apps.core.data_scope import scope_queryset


class ScopedLogViewSet(viewsets.ReadOnlyModelViewSet):
    def get_queryset(self):
        return scope_queryset(super().get_queryset(), self.request.user, 'log', 'user_id')


class OperationLogViewSet(ScopedLogViewSet):
    """操作日志查看"""
    queryset = OperationLog.objects.select_related('user').all()
    serializer_class = OperationLogSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'log:read'
    filterset_fields = ['action', 'resource', 'user']
    search_fields = ['description', 'user__username']
    ordering = ['-created_at']


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
