"""管理员诊断可靠事件；响应不包含业务 payload 或完整请求响应。"""
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.logs.models import OperationLog
from apps.permissions.permissions import IsAdmin
from .mixins import EnvelopeResponseMixin
from .events import _dispatch_after_commit
from .models import OutboxEvent
from .schema import envelope


class OutboxEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutboxEvent
        fields = ['id', 'topic', 'status', 'attempts', 'available_at', 'last_error',
                  'request_id', 'published_at', 'created_at', 'updated_at']
        read_only_fields = fields


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('OutboxDetailResponse', OutboxEventSerializer())),
    retry=extend_schema(request=None, responses=envelope('OutboxRetryResponse', OutboxEventSerializer())),
)
class OutboxEventViewSet(EnvelopeResponseMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsAdmin]
    queryset = OutboxEvent.objects.all()
    serializer_class = OutboxEventSerializer
    filterset_fields = ['status', 'topic']
    ordering_fields = ['created_at', 'available_at']
    ordering = ['-created_at']

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        with transaction.atomic():
            event = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
            if event.status != 'failed':
                return Response({'code': 409, 'message': '只能重试失败事件', 'data': None}, status=409)
            if event.topic == 'notification.delivery':
                return Response({'code': 409, 'message': '请通过通知投递记录执行授权重试', 'data': None}, status=409)
            if event.last_error == 'dispatch_exhausted' or (event.topic == 'task.failed' and event.attempts >= 5):
                return Response({'code': 409, 'message': '有限重试已耗尽，请通过任务中心检查和接续', 'data': None}, status=409)
            if event.topic == 'auth.email' and event.attempts >= 5:
                return Response({'code': 409, 'message': '邮件重试次数已用尽，请用户重新申请', 'data': None}, status=409)
            event.status = 'pending'
            event.available_at = timezone.now()
            event.save(update_fields=['status', 'available_at', 'updated_at'])
            OperationLog.objects.create(user=request.user, action='other', resource='outbox_event',
                                        resource_id=str(event.pk), description='人工重试失败事件',
                                        ip_address=request.META.get('REMOTE_ADDR') or '127.0.0.1')
            transaction.on_commit(_dispatch_after_commit)
            return Response({'code': 200, 'message': '已提交重试', 'data': self.get_serializer(event).data})
