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
                      'cleanup_history': 'task:delete', 'resume': 'task:retry'}
    filterset_fields = ['status', 'task_type', 'creator']
    search_fields = ['name', 'related_resource']
    ordering_fields = ['created_at', 'started_at', 'completed_at']
    ordering = ['-created_at']

    def get_queryset(self):
        from apps.core.data_scope import scope_queryset
        return scope_queryset(TaskRecord.objects.select_related('creator', 'import_execution__batch', 'maintenance_request').all(), self.request.user, 'task', 'creator_id')

    @extend_schema(request=None, responses={202: envelope('TaskResumedResponse', TaskRecordSerializer())})
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        source = self.get_object()
        from apps.data_io.execution import resume
        record = resume(request, source.pk)
        return Response({'code': 202, 'message': '已登记接续未提交行',
                         'data': TaskRecordSerializer(record).data}, status=202)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """取消执行中的任务（尽力撤销 Celery 任务并标记记录）"""
        visible = self.get_object()
        from django.db import transaction
        from .reliability import authorize
        from .models import ImportExecution, ImportBatch
        from apps.core.data_scope import scope_queryset
        from rest_framework.exceptions import NotFound
        from apps.logs.audit import snapshot, write_audit
        with transaction.atomic():
            actor = authorize(request, 'task:cancel')
            execution = ImportExecution.objects.filter(pk=visible.pk).first()
            if execution:
                ImportBatch.objects.select_for_update().get(pk=execution.batch_id)
            record = scope_queryset(TaskRecord.objects.select_for_update(), actor, 'task', 'creator_id').filter(pk=visible.pk).first()
            if record is None:
                raise NotFound()
            before = snapshot('task', record)
            maintenance = record.related_resource.startswith('maintenance:')
            if (maintenance and record.status != 'pending') or (record.status == 'running' and not execution):
                return Response({'code': 409, 'message': '已开始且不支持协作停止的任务不能取消', 'data': None}, status=409)
            if not record.mark_cancelled():
                return Response({'code': 409, 'message': '任务已完成，无法取消', 'data': None}, status=409)
            write_audit(request=request, actor=actor, resource='task', identifier=record.pk,
                        before=before, after=snapshot('task', record), record=record,
                        description='取消等待任务或停止后续导入行；已提交行保留')
            if maintenance:
                from apps.core.system_views import audit
                audit(request, 'maintenance_run', record.pk, {'status': 'pending'}, {'status': 'cancelled'})
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
