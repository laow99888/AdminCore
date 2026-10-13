"""
文件管理视图
"""

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiTypes
from apps.core.schema import MessageResponse, envelope

import json

from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F
from django.http import FileResponse, HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.logs.models import OperationLog
from apps.permissions.permissions import IsAdmin, HasPermission, has_permission_code
from apps.core.models import LifecycleConflict
from apps.core.exceptions import APIError

from .models import FileModel
from .serializers import (FileSerializer, FileUploadSerializer, RestoreSerializer,
                          RecycleActionSerializer, RecycleResultSerializer, RecyclePolicySerializer)


@extend_schema_view(
    create=extend_schema(responses={201: FileSerializer}),
    download=extend_schema(responses={(200, 'application/octet-stream'): OpenApiTypes.BINARY}),
    purge=extend_schema(responses=MessageResponse),
)
class FileViewSet(viewsets.ModelViewSet):
    """文件管理：上传 / 列表 / 下载 / 软删除"""
    permission_classes = [IsAuthenticated]
    filterset_fields = ['file_type', 'uploader']
    search_fields = ['original_name', 'description']
    ordering_fields = ['created_at', 'size', 'download_count']
    ordering = ['-created_at']
    permission_map = {'recycle': 'file:recycle', 'recycle_policy': 'file:recycle', 'restore': 'file:restore'}

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return FileModel.objects.none()
        # 头像有独立的本人鉴权入口，不能从一般文件/回收站 API 操作。
        queryset = FileModel.objects.select_related('uploader').filter(purpose='general')
        if self.action == 'recycle':
            queryset = queryset.filter(is_deleted=True)
        elif self.action not in {'restore', 'recycle_action', 'purge'}:
            queryset = queryset.filter(is_deleted=False)
        # 非管理员只能看到自己上传的文件
        from apps.core.data_scope import scope_queryset
        return scope_queryset(queryset, self.request.user, 'file', 'uploader_id', fallback='self')

    def get_serializer_class(self):
        if self.action == 'create':
            return FileUploadSerializer
        return FileSerializer

    @extend_schema(responses={(200, 'image/png'): OpenApiTypes.BINARY,
                              (200, 'application/pdf'): OpenApiTypes.BINARY,
                              413: MessageResponse, 415: MessageResponse, 422: MessageResponse})
    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        from .preview import preview_content
        instance = self.get_object()
        content, content_type = preview_content(instance)
        self._log('read', instance, f'Preview file {instance.original_name}')
        response = HttpResponse(content, content_type=content_type)
        # 不把用户文件名插入头；前端通过认证请求读取，PDF 仅绘制到 canvas。
        response['Content-Disposition'] = 'inline; filename="preview.pdf"' if content_type == 'application/pdf' else 'inline; filename="preview.png"'
        response['Content-Length'] = str(len(content))
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "sandbox; default-src 'none'; frame-ancestors 'none'"
        response['X-Frame-Options'] = 'DENY'
        return response

    def _log(self, action, instance, description=''):
        OperationLog.objects.create(
            user=self.request.user if self.request.user.is_authenticated else None,
            action=action,
            resource='file',
            resource_id=str(instance.id),
            description=description or instance.original_name,
            ip_address=self.request.META.get('REMOTE_ADDR', ''),
        )

    def create(self, request, *args, **kwargs):
        """上传文件后返回完整的文件信息（上传序列化器仅接收写入字段）"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            FileSerializer(serializer.instance, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_create(self, serializer):
        file_obj = serializer.save()
        self._log('upload', file_obj, f'Uploaded file {file_obj.original_name}')

    def perform_destroy(self, instance):
        with transaction.atomic():
            before = self._snapshot(instance)
            try:
                instance.soft_delete(actor=self.request.user)
            except LifecycleConflict as exc:
                raise APIError(str(exc), status_code=409) from exc
            self._lifecycle_log(instance, 'soft_delete', before)

    @staticmethod
    def _snapshot(instance):
        return {'is_deleted': instance.is_deleted,
                'deleted_at': instance.deleted_at.isoformat() if instance.deleted_at else None,
                'deleted_by': str(instance.deleted_by_id) if instance.deleted_by_id else None,
                'lifecycle_version': instance.lifecycle_version}

    def _lifecycle_log(self, instance, operation, before):
        self._log('update' if operation == 'restore' else 'delete', instance, json.dumps({
            'operation': operation, 'original_name': instance.original_name,
            'request_id': getattr(self.request, 'request_id', ''),
            'before': before, 'after': None if operation == 'purge' else self._snapshot(instance),
        }, ensure_ascii=False))

    @extend_schema(responses=FileSerializer(many=True))
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, HasPermission])
    def recycle(self, request):
        """同一数据范围的已删除文件，支持分页、筛选和搜索。"""
        return self.list(request)

    @extend_schema(responses=envelope('FileRecyclePolicyResponse', RecyclePolicySerializer()))
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, HasPermission])
    def recycle_policy(self, request):
        from apps.core.system_config import config_value
        from apps.core.modules import task_enabled
        from django_celery_beat.models import PeriodicTask
        return Response({'code': 200, 'message': 'success', 'data': {'retention_days': config_value('files.retention_days'),
                         'cleanup_enabled': task_enabled('tasks.cleanup_soft_deleted_files') and
                         PeriodicTask.objects.filter(task='tasks.cleanup_soft_deleted_files', enabled=True).exists()}})

    @extend_schema(request=RestoreSerializer, responses=envelope('FileRestoreResponse', FileSerializer()))
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, HasPermission])
    def restore(self, request, pk=None):
        serializer = RestoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            # 必须先按数据范围查询，再锁定；不能从全表按 ID 取回文件。
            try:
                instance = self.get_queryset().select_for_update(of=('self',)).filter(pk=pk).first()
            except DjangoValidationError as exc:
                raise APIError('文件不存在', status_code=404) from exc
            if instance is None:
                raise APIError('文件不存在', status_code=404)
            before = self._snapshot(instance)
            try:
                instance.restore(serializer.validated_data['lifecycle_version'])
            except LifecycleConflict as exc:
                raise APIError(str(exc), status_code=409) from exc
            except OSError as exc:
                raise APIError('存储暂时不可用，请稍后重试', status_code=503) from exc
            self._lifecycle_log(instance, 'restore', before)
        return Response({'code': 200, 'message': '已恢复', 'data': FileSerializer(instance, context=self.get_serializer_context()).data})

    @extend_schema(request=RecycleActionSerializer, responses=envelope('FileRecycleActionResponse', RecycleResultSerializer()))
    @action(detail=False, methods=['post'])
    def recycle_action(self, request):
        """最多 100 项；逐项复核范围/版本。部分成功有明确逐项结果，不承诺整批原子性。"""
        serializer = RecycleActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        operation = data['action']
        if not has_permission_code(request.user, 'file:' + operation):
            raise APIError('没有权限访问', status_code=403)
        results = []
        for item in data['items']:
            result = {'id': str(item['id'])}
            try:
                with transaction.atomic():
                    instance = self.get_queryset().select_for_update(of=('self',)).filter(pk=item['id']).first()
                    if instance is None:
                        raise APIError('文件不存在', status_code=404)
                    instance.check_lifecycle_version(item['lifecycle_version'])
                    if not instance.is_deleted:
                        raise LifecycleConflict('文件不在回收站，请刷新后重试')
                    if data['dry_run']:
                        pass
                    elif operation == 'restore':
                        before = self._snapshot(instance)
                        instance.restore(item['lifecycle_version'])
                        self._lifecycle_log(instance, 'restore', before)
                    else:
                        instance.hard_delete(expected_version=item['lifecycle_version'], audit=lambda row: self._lifecycle_log(row, 'purge', self._snapshot(row)))
                    result.update(status=200, message='可执行' if data['dry_run'] else '已完成',
                                  original_name=instance.original_name, size=instance.size)
            except LifecycleConflict as exc:
                result.update(status=409, message=str(exc))
            except APIError as exc:
                result.update(status=exc.status_code, message=str(exc.detail))
            except OSError:
                # 外部存储错误不泄露服务器路径、签名或凭据；记录和失败项可重试。
                result.update(status=503, message='存储暂时不可用，请稍后重试')
            results.append(result)
        succeeded = sum(item['status'] == 200 for item in results)
        if not data['dry_run']:
            OperationLog.objects.create(
                user=request.user, action='other', resource='file', resource_id='',
                ip_address=request.META.get('REMOTE_ADDR') or '127.0.0.1',
                description=json.dumps({'operation': 'batch_' + operation,
                                       'request_id': getattr(request, 'request_id', ''),
                                       'results': results, 'succeeded': succeeded,
                                       'failed': len(results) - succeeded}, ensure_ascii=False),
            )
        return Response({'code': 200, 'message': '已处理', 'data': {
            'results': results, 'dry_run': data['dry_run'],
            'succeeded': succeeded, 'failed': len(results) - succeeded,
        }})

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """下载文件（记录下载次数）"""
        file_obj = self.get_object()
        if not file_obj.file or not file_obj.file.storage.exists(file_obj.file.name):
            return Response({'code': 404, 'message': '文件不存在', 'data': None}, status=status.HTTP_404_NOT_FOUND)

        FileModel.objects.filter(id=file_obj.id).update(download_count=F('download_count') + 1)
        self._log('download', file_obj, f'Downloaded file {file_obj.original_name}')

        response = FileResponse(file_obj.file.open('rb'), as_attachment=True, filename=file_obj.original_name)
        return response

    @action(detail=True, methods=['delete'], permission_classes=[IsAuthenticated, IsAdmin])
    def purge(self, request, pk=None):
        """物理删除文件（仅管理员）"""
        try:
            file_obj = self.get_queryset().filter(pk=pk).first()
        except DjangoValidationError as exc:
            raise APIError('文件不存在', status_code=404) from exc
        if not file_obj:
            return Response({'code': 404, 'message': '文件不存在', 'data': None}, status=status.HTTP_404_NOT_FOUND)
        try:
            file_obj.hard_delete(expected_version=file_obj.lifecycle_version,
                                 audit=lambda row: self._lifecycle_log(row, 'purge', self._snapshot(row)))
        except LifecycleConflict as exc:
            raise APIError(str(exc), status_code=409) from exc
        except OSError as exc:
            raise APIError('存储暂时不可用，请稍后重试', status_code=503) from exc
        return Response({'code': 200, 'message': '文件已彻底删除', 'data': None})
