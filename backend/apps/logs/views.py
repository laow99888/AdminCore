"""
日志查看视图
"""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import OperationLog, LoginLog, ExceptionLog
from .serializers import OperationLogSerializer, LoginLogSerializer, ExceptionLogSerializer
from apps.permissions.permissions import HasPermission


class OperationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """操作日志查看"""
    queryset = OperationLog.objects.all()
    serializer_class = OperationLogSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'log:read'
    filterset_fields = ['action', 'resource', 'user']
    search_fields = ['description', 'user__username']
    ordering = ['-created_at']


class LoginLogViewSet(viewsets.ReadOnlyModelViewSet):
    """登录日志查看"""
    queryset = LoginLog.objects.all()
    serializer_class = LoginLogSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'log:read'
    filterset_fields = ['status', 'username']
    search_fields = ['username']
    ordering = ['-created_at']


class ExceptionLogViewSet(viewsets.ReadOnlyModelViewSet):
    """异常日志查看"""
    queryset = ExceptionLog.objects.all()
    serializer_class = ExceptionLogSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'log:read'
    filterset_fields = ['level', 'request_method']
    search_fields = ['message', 'request_path']
    ordering = ['-created_at']
