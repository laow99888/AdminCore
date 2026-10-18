"""后台业务导出入口；产物只向发起者提供经当前授权复核的下载。"""
import hashlib
from datetime import timedelta

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.core.events import enqueue_event
from apps.core.schema import envelope
from apps.core.tenancy import current_tenant_id
from apps.tasks.models import TaskRecord
from apps.tasks.reliability import authorize, policy
from apps.tasks.serializers import TaskRecordSerializer
from .business_export import prepare, checked_actor, guarded_batch, MAX_BYTES, BATCH_SIZE
from .business_views import response
from .models import BusinessExportRequest
from .views import DataModuleView, _log


class ExportRequestSerializer(serializers.Serializer):
    resource = serializers.RegexField(r'^[a-z][a-z0-9_]{0,19}$')
    format = serializers.ChoiceField(choices=['csv', 'xlsx'])
    filters = serializers.DictField(child=serializers.CharField(allow_blank=True), default=dict)


def own_request(actor, identifier):
    execution = BusinessExportRequest.objects.select_related('record').filter(
        pk=identifier, record__creator=actor, tenant_id=current_tenant_id()).first()
    if execution is None:
        raise NotFound()
    return execution


class BusinessExportCreateView(DataModuleView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ExportRequestSerializer, responses={202: envelope('BusinessExportCreated', TaskRecordSerializer())})
    def post(self, request):
        serializer = ExportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        with transaction.atomic():
            actor = authorize(request, 'data_io:export')
            if BusinessExportRequest.objects.filter(record__creator=actor,
                    record__status__in=['pending', 'running']).count() >= 3:
                raise ValidationError('同时最多三个后台导出，请等待已有任务完成')
            options, snapshot = prepare(actor, values['resource'], values['filters'], values['format'])
            record = TaskRecord.objects.create(name='业务导出：' + values['resource'], task_type='export',
                related_resource=values['resource'], creator=actor,
                result={'documents': len(snapshot), 'rows': 0})
            BusinessExportRequest.objects.create(record=record, resource=values['resource'], options=options,
                snapshot=snapshot, policy=policy('import'), session_version=actor.session_version,
                session_id=request.auth.get('sid') if request.auth is not None else None,
                request_id=str(getattr(request, 'request_id', ''))[:100], expires_at=timezone.now() + timedelta(days=1))
            record.celery_task_id = str(record.pk)
            record.save(update_fields=['celery_task_id', 'updated_at'])
            enqueue_event('export.requested', 'export:' + str(record.pk), {'record_id': str(record.pk)}, request)
            _log(request, 'export', '登记后台业务导出：' + values['resource'], str(record.pk))
        return response(TaskRecordSerializer(record).data, 202)


class BusinessExportStatusView(DataModuleView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=envelope('BusinessExportStatus', TaskRecordSerializer()))
    def get(self, request, task_id):
        with transaction.atomic():
            actor = authorize(request, 'data_io:export')
            execution = own_request(actor, task_id)
            checked_actor(execution, lock=True)
            return response(TaskRecordSerializer(execution.record).data)


class BusinessExportDownloadView(DataModuleView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={(200, 'application/octet-stream'): bytes})
    def get(self, request, task_id):
        # 用户锁覆盖全部复核和读取，授权管理同样先锁用户；不缓存旧授权。
        with transaction.atomic():
            actor = authorize(request, 'data_io:export')
            execution = own_request(actor, task_id)
            checked_actor(execution, lock=True)
            record = TaskRecord.objects.select_for_update().get(pk=task_id)
            if record.status != 'success' or not execution.artifact or timezone.now() >= execution.expires_at:
                raise ValidationError('导出未完成或已过期，请重新提交')
            for start in range(0, len(execution.snapshot), BATCH_SIZE):
                guarded_batch(execution, execution.snapshot[start:start + BATCH_SIZE], verify_hash=True)
            try:
                with execution.artifact.open('rb') as stream:
                    raw = stream.read(MAX_BYTES + 1)
            except OSError:
                raise ValidationError('导出文件不可用，请重新提交') from None
            if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != execution.artifact_sha256:
                raise ValidationError('导出文件不可用，请重新提交')
            _log(request, 'export', '下载后台业务导出：' + execution.resource, str(task_id))
        format_name = execution.options['format']
        mime = 'text/csv; charset=utf-8' if format_name == 'csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        result = HttpResponse(raw, content_type=mime)
        result['Content-Disposition'] = 'attachment; filename="' + execution.resource + '.' + format_name + '"'
        result['X-Content-Type-Options'] = 'nosniff'
        return result
