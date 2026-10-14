"""
任务中心视图
"""

import logging

from drf_spectacular.utils import extend_schema, extend_schema_view
from apps.core.schema import envelope, MessageResponse
from apps.core.schema import CleanupRequestSerializer

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.permissions.permissions import HasPermission

from .models import TaskRecord
from .serializers import TaskRecordSerializer

logger = logging.getLogger(__name__)


@extend_schema_view(
    cancel=extend_schema(request=None, responses=envelope('TaskCancelledResponse', TaskRecordSerializer())),
    cleanup_history=extend_schema(request=CleanupRequestSerializer, responses=MessageResponse),
)
class TaskRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """任务中心：查看任务记录、取消任务、清理历史"""
    serializer_class = TaskRecordSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'list': 'task:read', 'retrieve': 'task:read', 'cancel': 'task:cancel',
                      'cleanup_history': 'task:delete'}
    filterset_fields = ['status', 'task_type', 'creator']
    search_fields = ['name', 'related_resource']
    ordering_fields = ['created_at', 'started_at', 'completed_at']
    ordering = ['-created_at']

    def get_queryset(self):
        from apps.core.data_scope import scope_queryset
        return scope_queryset(TaskRecord.objects.select_related('creator').all(), self.request.user, 'task', 'creator_id')

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """取消执行中的任务（尽力撤销 Celery 任务并标记记录）"""
        record = self.get_object()
        if record.related_resource.startswith('maintenance:'):
            from django.utils import timezone
            from django.db import transaction
            from apps.core.system_views import audit
            with transaction.atomic():
                changed = TaskRecord.objects.filter(pk=record.pk, status='pending').update(
                    status='cancelled', completed_at=timezone.now(), updated_at=timezone.now())
                if not changed:
                    return Response({'code': 409, 'message': '维护任务已开始或已完成，不能取消已开始的维护操作', 'data': None}, status=409)
                record.refresh_from_db()
                audit(request, 'maintenance_run', record.pk, {'status': 'pending'}, {'status': 'cancelled'})
            return Response({'code': 200, 'message': '等待执行的维护任务已取消', 'data': TaskRecordSerializer(record).data})
        if record.status not in ('pending', 'running'):
            return Response({'code': 400, 'message': f'任务当前状态为 {record.status}，无法取消', 'data': None},
                            status=status.HTTP_400_BAD_REQUEST)

        if not record.mark_cancelled():
            return Response({'code': 400, 'message': '任务已完成，无法取消', 'data': None}, status=400)
        revoked = False
        if record.celery_task_id:
            try:
                from config.celery import app as celery_app
                # 运行中任务协作取消；不杀死可能已被复用的 worker 进程。
                celery_app.control.revoke(record.celery_task_id, terminate=False)
                revoked = True
            except Exception as exc:
                # broker 不可用时仅标记记录，不阻断取消流程
                logger.warning('Revoke celery task %s failed: %s', record.celery_task_id, exc)

        return Response({
            'code': 200,
            'message': '已请求取消；已完成的导入行保留，后续行停止执行' + ('（已发送撤销指令）' if revoked else ''),
            'data': TaskRecordSerializer(record).data,
        })

    @action(detail=False, methods=['post'], url_path='cleanup')
    def cleanup_history(self, request):
        """清理已完成的历史任务记录（默认保留 30 天）"""
        from datetime import timedelta
        from django.utils import timezone

        serializer = CleanupRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        days = serializer.validated_data['days']
        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = self.get_queryset().filter(
            status__in=['success', 'failed', 'cancelled'],
            created_at__lt=cutoff,
        ).delete()
        return Response({'code': 200, 'message': f'已清理 {deleted} 条历史任务记录', 'data': None})
