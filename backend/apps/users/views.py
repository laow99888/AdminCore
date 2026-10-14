"""
用户管理视图
"""

from drf_spectacular.utils import extend_schema, extend_schema_view
from apps.core.schema import envelope, MessageResponse
from apps.core.schema import ResetPasswordRequestSerializer

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
import logging
from .serializers import (
    UserDetailSerializer, UserListSerializer, UserCreateSerializer,
    UserUpdateSerializer, BulkUserActionSerializer,
    SensitiveContactRequestSerializer, SensitiveContactSerializer
)
from apps.permissions.permissions import HasPermission, has_permission_code
from apps.logs.models import OperationLog
from apps.core.mixins import EnvelopeResponseMixin

User = get_user_model()
logger = logging.getLogger(__name__)


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('UserDetailResponse', UserDetailSerializer())),
    create=extend_schema(responses={201: envelope('UserCreatedResponse', UserCreateSerializer())}),
    update=extend_schema(responses=envelope('UserUpdatedResponse', UserUpdateSerializer())),
    partial_update=extend_schema(responses=envelope('UserPatchedResponse', UserUpdateSerializer())),
    destroy=extend_schema(responses={200: MessageResponse}),
    bulk_action=extend_schema(request=BulkUserActionSerializer, responses=MessageResponse),
    reset_password=extend_schema(request=ResetPasswordRequestSerializer, responses=MessageResponse),
    sensitive=extend_schema(request=SensitiveContactRequestSerializer,
                           responses=envelope('SensitiveContactResponse', SensitiveContactSerializer())),
)
class UserViewSet(EnvelopeResponseMixin, viewsets.ModelViewSet):
    """用户管理"""
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'list': 'user:read', 'retrieve': 'user:read', 'create': 'user:create',
                      'update': 'user:update', 'partial_update': 'user:update', 'destroy': 'user:delete',
                      'reset_password': 'user:update', 'bulk_action': 'user:update',
                      'sensitive': 'user:sensitive_read'}
    filterset_fields = ['is_active']
    search_fields = ['username', 'first_name', 'last_name']
    ordering_fields = ['created_at', 'username', 'login_count']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = User.objects.all()
        if self.action != 'list':
            queryset = queryset.select_related('profile')
        if self.action not in ('list', 'retrieve', 'sensitive') and not (self.request.user.is_staff or self.request.user.is_superuser):
            queryset = queryset.filter(is_staff=False, is_superuser=False)
        from apps.core.data_scope import scope_queryset
        return scope_queryset(queryset, self.request.user, 'user', 'pk')

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action == 'list':
            return UserListSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserDetailSerializer

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def sensitive(self, request, pk=None):
        """单次查看联系方式：权限、数据范围、会话与密码共同约束。"""
        from apps.core.data_scope import scope_queryset
        from apps.auth_app.reauthentication import require_recent_password
        serializer = SensitiveContactRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # 固定用户锁顺序，避免两个管理员互相查看造成死锁。
        visible = scope_queryset(User.objects.all(), request.user, 'user', 'pk')
        target_id = get_object_or_404(visible, pk=pk).pk
        locked = list(User.objects.select_for_update().filter(
            pk__in=[request.user.pk, target_id]).order_by('pk'))
        actor = next((user for user in locked if user.pk == request.user.pk), None)
        if actor is None:
            raise AuthenticationFailed('登录凭据已撤销，请重新登录')
        if not all(has_permission_code(actor, code) for code in ('user:read', 'user:sensitive_read')):
            raise PermissionDenied('没有查看用户联系方式原值的权限')
        require_recent_password(request, actor, 'user:sensitive-read')
        # 锁内重新计算有效角色与范围，不沿用旧请求对象的授权状态。
        target = get_object_or_404(scope_queryset(User.objects.all(), actor, 'user', 'pk'), pk=target_id)
        OperationLog.objects.create(user=actor, action='read_sensitive', resource='user',
                                    resource_id=str(target.pk), description='查看用户邮箱与手机号原值',
                                    ip_address=request.META.get('REMOTE_ADDR', ''))
        return Response({'code': 200, 'message': '原值仅供本次查看',
                         'data': SensitiveContactSerializer(target).data})

    @transaction.atomic
    def perform_create(self, serializer):
        from apps.core.data_scope import unrestricted_user_creation
        from rest_framework.exceptions import PermissionDenied
        if not unrestricted_user_creation(self.request.user):
            raise PermissionDenied('受限数据范围不能创建未分配部门的用户，请由管理员创建并分配')
        user = serializer.save()
        from apps.logs.audit import snapshot, write_audit
        write_audit(request=self.request, resource='user', identifier=user.pk, action='create',
                    after=snapshot('user', user))

    @transaction.atomic
    def perform_destroy(self, instance):
        from apps.logs.audit import snapshot, write_audit
        instance = User.objects.select_for_update().get(pk=instance.pk)
        write_audit(request=self.request, resource='user', identifier=instance.pk, action='delete',
                    before=snapshot('user', instance))
        instance.delete()

    @transaction.atomic
    def perform_update(self, serializer):
        from apps.logs.audit import snapshot, write_audit
        serializer.instance = User.objects.select_for_update().get(pk=serializer.instance.pk)
        before = snapshot('user', serializer.instance)
        user = serializer.save()
        write_audit(request=self.request, resource='user', identifier=user.pk,
                    before=before, after=snapshot('user', user))

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
                    from apps.logs.audit import snapshot, write_audit
                    users = self.get_queryset().filter(id__in=user_ids).select_for_update(of=('self',)).order_by('pk')
                    rows = list(users.prefetch_related('roles'))
                    if len(set(user_ids)) != len(user_ids) or len(rows) != len(user_ids):
                        write_audit(request=request, resource='user', action='other', status=403,
                            description='batch_rejected', results=[{'id': identifier, 'status': 403} for identifier in user_ids])
                        return Response({'code': 403, 'message': '批量请求包含重复、不可访问或不存在的用户，未执行变更', 'data': None}, status=403)

                    before = {row.pk: snapshot('user', row) for row in rows}

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

                    for row in rows:
                        after = {**before[row.pk], 'is_active': action == 'activate'} if action != 'delete' else None
                        write_audit(request=request, resource='user', identifier=row.pk, action=action,
                                    before=before[row.pk], after=after)
                    write_audit(request=request, resource='user', action=action,
                                description=f'{desc}: {len(user_ids)} users',
                                results=[{'id': identifier, 'status': 200} for identifier in user_ids])

                    return Response({
                        'code': 200,
                        'message': f'{action} success',
                        'data': None,
                    })
            except Exception:
                logger.exception('批量用户操作失败')
                return Response({
                    'code': 500,
                    'message': '批量操作失败，请查看服务器日志',
                    'data': None,
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'code': 400,
            'message': 'Invalid request',
            'data': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reset_password(self, request, pk=None):
        """重置用户密码"""
        user = self.get_object()
        user = User.objects.select_for_update().get(pk=user.pk)
        from apps.logs.audit import snapshot, write_audit
        before = snapshot('user', user)
        serializer = ResetPasswordRequestSerializer(data=request.data, context={'user': user})
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data['password'])
        user.must_change_password = serializer.validated_data['must_change_password']
        user.session_version += 1
        user.save(update_fields=['password', 'must_change_password', 'session_version', 'updated_at'])

        write_audit(request=request, resource='user', identifier=user.pk,
                    before=before, after=snapshot('user', user), description='reset_password')

        return Response({
            'code': 200,
            'message': 'Password reset successfully',
            'data': None,
        })
