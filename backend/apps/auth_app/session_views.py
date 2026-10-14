"""本人会话与管理员在线用户目录；所有撤销均在用户锁之后锁会话。"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.data_scope import scope_queryset
from apps.core.schema import envelope
from apps.permissions.permissions import HasPermission, IsAdmin
from .models import AuthSession
from .sessions import active_sessions, audit_session, locked_request_session, session_id

User = get_user_model()


class PasswordConfirmationSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=4096)


class SessionRevokeResultSerializer(serializers.Serializer):
    revoked_count = serializers.IntegerField()


class PersonalSessionSerializer(serializers.ModelSerializer):
    is_current = serializers.SerializerMethodField()
    active = serializers.SerializerMethodField()

    def get_is_current(self, instance) -> bool:
        return instance.pk == session_id(self.context['request'].auth)

    def get_active(self, instance) -> bool:
        return True

    class Meta:
        model = AuthSession
        fields = ('id', 'created_at', 'last_seen_at', 'expires_at', 'ip_address',
                  'user_agent', 'is_current', 'active')
        read_only_fields = fields


class NoStoreSessionMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response


@extend_schema_view(destroy=extend_schema(request=PasswordConfirmationSerializer,
    responses=envelope('PersonalSessionRevoked', SessionRevokeResultSerializer())))
class PersonalSessionViewSet(NoStoreSessionMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PersonalSessionSerializer
    filter_backends = []
    lookup_value_regex = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'

    def get_queryset(self):
        return active_sessions().filter(user=self.request.user).order_by('-last_seen_at', '-id')

    @transaction.atomic
    def destroy(self, request, pk=None):
        from .reauthentication import require_recent_password
        actor = User.objects.select_for_update().filter(pk=request.user.pk).first()
        if actor is None:
            raise AuthenticationFailed('登录凭据已撤销，请重新登录')
        locked_request_session(request, actor)
        require_recent_password(request, actor, 'session:revoke')
        target = get_object_or_404(AuthSession.objects.select_for_update().filter(user=actor), pk=pk)
        if target.revoked_at is None:
            target.revoked_at = timezone.now()
            target.save(update_fields=['revoked_at'])
            audit_session(request, actor, 'revoke_own_session', target.pk)
            count = 1
        else:
            count = 0
        return Response({'code': 200, 'message': '会话已撤销', 'data': {'revoked_count': count}})


class OnlineUserSerializer(serializers.ModelSerializer):
    session_count = serializers.IntegerField(read_only=True)
    last_seen_at = serializers.DateTimeField(read_only=True)
    is_current_user = serializers.SerializerMethodField()

    def get_is_current_user(self, instance) -> bool:
        return instance.pk == self.context['request'].user.pk

    class Meta:
        model = User
        fields = ('id', 'username', 'first_name', 'last_name', 'session_count',
                  'last_seen_at', 'is_current_user')
        read_only_fields = fields


@extend_schema_view(revoke=extend_schema(request=PasswordConfirmationSerializer,
    responses=envelope('OnlineUserRevoked', SessionRevokeResultSerializer())))
class OnlineUserViewSet(NoStoreSessionMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsAdmin, HasPermission]
    permission_map = {'list': 'session:read', 'revoke': 'session:revoke'}
    serializer_class = OnlineUserSerializer
    search_fields = ['username', 'first_name', 'last_name']
    filterset_fields = []
    ordering_fields = []
    lookup_value_regex = PersonalSessionViewSet.lookup_value_regex

    def get_queryset(self):
        # 数据范围入口始终调用；staff/superuser 沿用仓库的全范围规则。
        users = scope_queryset(User.objects.all(), self.request.user, 'user', 'pk')
        return users.filter(jwt_sessions__in=active_sessions()).annotate(
            session_count=Count('jwt_sessions'), last_seen_at=Max('jwt_sessions__last_seen_at')
        ).order_by('-last_seen_at', 'id')

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def revoke(self, request, pk=None):
        from .reauthentication import require_recent_password
        # 同时锁用户且固定 UUID 顺序，避免管理员互相撤销导致死锁。
        visible = scope_queryset(User.objects.all(), request.user, 'user', 'pk')
        target_id = get_object_or_404(visible, pk=pk).pk
        if target_id == request.user.pk:
            raise PermissionDenied('不能在管理目录撤销自己的全部会话，请在本人会话管理操作')
        locked = list(User.objects.select_for_update().filter(
            pk__in=[request.user.pk, target_id]).order_by('pk'))
        by_id = {user.pk: user for user in locked}
        actor = by_id.get(request.user.pk)
        target = by_id.get(target_id)
        if actor is None or target is None:
            raise PermissionDenied('账户已不可访问')
        locked_request_session(request, actor)
        require_recent_password(request, actor, 'session:admin-revoke-all')
        # 等待锁期间管理员权限变化必须重新检查。
        if not (actor.is_staff or actor.is_superuser):
            raise PermissionDenied('管理员权限已变化')
        from apps.permissions.permissions import has_permission_code
        if not has_permission_code(actor, 'session:revoke'):
            raise PermissionDenied('没有撤销会话的权限')
        get_object_or_404(scope_queryset(User.objects.all(), actor, 'user', 'pk'), pk=target.pk)
        count = active_sessions().filter(user=target).count()
        # 用户行串行化全部会话修改；UPDATE 自身取得会话行锁，避免载入全部历史记录。
        AuthSession.objects.filter(user=target, revoked_at__isnull=True).update(revoked_at=timezone.now())
        target.session_version += 1
        target.save(update_fields=['session_version', 'updated_at'])
        audit_session(request, actor, 'revoke_user_sessions', target.pk)
        return Response({'code': 200, 'message': '该用户全部设备已下线', 'data': {'revoked_count': count}})
