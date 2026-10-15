"""
通知中心视图
"""

from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from apps.core.schema import envelope
from apps.core.query_budget import QueryBudgetListMixin

from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.permissions.permissions import IsAdmin
from apps.core.idempotency import with_idempotency

from .models import Notification
from .serializers import NotificationCreateSerializer, NotificationSerializer


@extend_schema_view(
    create=extend_schema(responses={201: envelope('NotificationSentResponse', inline_serializer('SentCount',fields={'sent_count':serializers.IntegerField()}))}),
    retrieve=extend_schema(responses=envelope('NotificationDetailResponse', NotificationSerializer())),
    mark_read=extend_schema(request=None, responses=envelope('NotificationReadResponse', NotificationSerializer())),
    mark_all_read=extend_schema(request=None, responses=envelope('NotificationsReadResponse', inline_serializer('UpdatedCount',fields={'updated':serializers.IntegerField()}))),
    unread_count=extend_schema(responses=envelope('UnreadCountResponse', inline_serializer('UnreadCount',fields={'count':serializers.IntegerField()}))),
)
class NotificationViewSet(QueryBudgetListMixin, mixins.ListModelMixin,
                          mixins.RetrieveModelMixin,
                          mixins.CreateModelMixin,
                          viewsets.GenericViewSet):
    """通知中心：我的通知列表 / 标记已读 / 未读数；管理员可发送通知"""
    permission_classes = [IsAuthenticated]
    filterset_fields = ['notification_type', 'is_read']
    search_fields = ['title', 'content']
    ordering_fields = ['created_at', 'read_at']
    ordering = ['-created_at']
    list_query_choices = {'scope': ('', 'all')}

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Notification.objects.none()
        # 普通用户只能看到自己的通知；管理员可查全部（?scope=all）
        queryset = Notification.objects.select_related('recipient', 'sender')
        if not (self.request.user.is_staff and self.request.query_params.get('scope') == 'all'):
            queryset = queryset.filter(recipient=self.request.user)
        return queryset

    def get_serializer_class(self):
        if self.action == 'create':
            return NotificationCreateSerializer
        return NotificationSerializer

    def get_permissions(self):
        # 发送通知仅管理员
        if self.action == 'create':
            return [IsAuthenticated(), IsAdmin()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        """发送通知（仅管理员）"""
        def action():
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            result = serializer.save()
            return Response({'code': 200, 'message': '发送成功', 'data': result}, status=status.HTTP_201_CREATED)
        return with_idempotency(request, 'notifications:create', action)

    def retrieve(self, request, *args, **kwargs):
        """查看详情时自动标记为已读"""
        instance = self.get_object()
        instance.mark_read()
        return Response({'code': 200, 'message': 'success', 'data': NotificationSerializer(instance).data})

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """标记单条通知为已读"""
        notification = self.get_object()
        notification.mark_read()
        return Response({'code': 200, 'message': '已标记为已读', 'data': NotificationSerializer(notification).data})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """标记全部通知为已读"""
        now = timezone.now()
        updated = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True, read_at=now)
        from apps.core.error_i18n import error_text
        return Response({'code': 200, 'message': error_text('已将 {count} 条通知标记为已读', count=updated), 'data': {'updated': updated}})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """未读通知数量"""
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'code': 200, 'message': 'ok', 'data': {'count': count}})
