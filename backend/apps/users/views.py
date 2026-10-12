"""
用户管理视图
"""

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.contrib.auth import get_user_model
from django.db import transaction
from .serializers import (
    UserDetailSerializer, UserListSerializer, UserCreateSerializer,
    UserUpdateSerializer, BulkUserActionSerializer
)
from apps.permissions.permissions import HasPermission
from apps.logs.models import OperationLog
from apps.core.mixins import EnvelopeResponseMixin

User = get_user_model()


class UserViewSet(EnvelopeResponseMixin, viewsets.ModelViewSet):
    """用户管理"""
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'list': 'user:read', 'retrieve': 'user:read', 'create': 'user:create',
                      'update': 'user:update', 'partial_update': 'user:update', 'destroy': 'user:delete',
                      'reset_password': 'user:update', 'bulk_action': 'user:update'}
    filterset_fields = ['is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['created_at', 'username', 'login_count']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = User.objects.select_related('profile').all()
        if self.action not in ('list', 'retrieve') and not (self.request.user.is_staff or self.request.user.is_superuser):
            queryset = queryset.filter(is_staff=False, is_superuser=False)
        return queryset

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action == 'list':
            return UserListSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserDetailSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        # 记录操作日志
        OperationLog.objects.create(
            user=self.request.user,
            action='create',
            resource='user',
            resource_id=str(user.id),
            description=f'Created user {user.username}',
            ip_address=self.request.META.get('REMOTE_ADDR', ''),
        )

    def perform_destroy(self, instance):
        # 记录操作日志
        OperationLog.objects.create(
            user=self.request.user,
            action='delete',
            resource='user',
            resource_id=str(instance.id),
            description=f'Deleted user {instance.username}',
            ip_address=self.request.META.get('REMOTE_ADDR', ''),
        )
        instance.delete()

    @action(detail=False, methods=['post'])
    def bulk_action(self, request):
        """批量操作用户"""
        serializer = BulkUserActionSerializer(data=request.data)
        if serializer.is_valid():
            user_ids = serializer.validated_data['user_ids']
            action = serializer.validated_data['action']
            from apps.permissions.permissions import has_permission_code
            if action == 'delete' and not has_permission_code(request.user, 'user:delete'):
                return Response({'code': 403, 'message': '没有删除用户的权限', 'data': None}, status=403)

            try:
                with transaction.atomic():
                    users = self.get_queryset().filter(id__in=user_ids)

                    if action == 'activate':
                        users.update(is_active=True)
                        desc = 'Activated users'
                    elif action == 'deactivate':
                        users.update(is_active=False)
                        desc = 'Deactivated users'
                    elif action == 'delete':
                        count = users.count()
                        users.delete()
                        desc = f'Deleted {count} users'

                    # 记录操作日志
                    OperationLog.objects.create(
                        user=request.user,
                        action=action,
                        resource='user',
                        description=f'{desc}: {len(user_ids)} users',
                        ip_address=request.META.get('REMOTE_ADDR', ''),
                    )

                    return Response({
                        'code': 200,
                        'message': f'{action} success',
                        'data': None,
                    })
            except Exception as e:
                return Response({
                    'code': 500,
                    'message': str(e),
                    'data': None,
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'code': 400,
            'message': 'Invalid request',
            'data': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        """重置用户密码"""
        user = self.get_object()
        new_password = request.data.get('password')

        if not new_password:
            return Response({
                'code': 400,
                'message': 'Password required',
                'data': None,
            }, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()

        OperationLog.objects.create(
            user=request.user,
            action='update',
            resource='user',
            resource_id=str(user.id),
            description=f'Reset password for {user.username}',
            ip_address=request.META.get('REMOTE_ADDR', ''),
        )

        return Response({
            'code': 200,
            'message': 'Password reset successfully',
            'data': None,
        })
