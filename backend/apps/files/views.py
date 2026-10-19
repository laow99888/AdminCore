"""
文件管理视图
"""

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiTypes
from apps.core.schema import MessageResponse, envelope

import json

from django.db import transaction
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F, Q
from django.http import FileResponse, HttpResponse
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import APIException
from apps.auth_app.write_authorization import authorize_write
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.logs.models import OperationLog
from apps.permissions.permissions import IsAdmin, HasPermission, has_permission_code
from apps.core.models import LifecycleConflict
from apps.core.exceptions import APIError
from apps.core.query_budget import QueryBudgetListMixin
from apps.core.client_ip import request_ip

from .models import FileModel, FileAccessGrant
from .filters import FileFilter
from .serializers import (FileSerializer, FileUploadSerializer, RestoreSerializer,
                          RecycleActionSerializer, RecycleResultSerializer, RecyclePolicySerializer,
                          ImageTransformSerializer, ImageProcessingConfigSerializer,
                          FileACLSerializer)


class FileReferenceStatusSerializer(serializers.Serializer):
    protected = serializers.BooleanField()
    lifecycle_version = serializers.IntegerField()


@extend_schema_view(
    create=extend_schema(description='上传返回统一 code/message/data；v1 兼容期保留顶层文件字段，新调用方只读取 data。', responses={201: envelope('FileUploadedResponse', FileSerializer())}),
    download=extend_schema(responses={(200, 'application/octet-stream'): OpenApiTypes.BINARY}),
    purge=extend_schema(responses={202: MessageResponse}),
)
class FileViewSet(QueryBudgetListMixin, viewsets.ModelViewSet):
    """文件管理：上传 / 列表 / 下载 / 软删除"""
    permission_classes = [IsAuthenticated]
    # 文件元数据全部只读；不提供可能保存旧实例的空 PUT/PATCH 写入口。
    # 保留 PUT/PATCH 供 ACL 替换动作使用；文件本体元数据通过 update hooks 明确拒绝。
    http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
    filterset_class = FileFilter
    search_fields = ['original_name', 'description']
    ordering_fields = ['created_at', 'size', 'download_count']
    ordering = ['-created_at']
    permission_map = {'create': 'file:upload', 'download': 'file:download', 'preview': 'file:download', 'recycle': 'file:recycle', 'recycle_policy': 'file:recycle', 'restore': 'file:restore',
                      'transform': 'file:process', 'processing_config': 'file:process', 'acl': 'file:upload', 'references': 'file:read'}

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action in ('create', 'download', 'preview', 'references'):
            permissions.append(HasPermission())
        return permissions

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return FileModel.objects.none()
        # 头像有独立的本人鉴权入口，不能从一般文件/回收站 API 操作。
        queryset = FileModel.objects.select_related('uploader').filter(purpose='general')
        if self.action == 'recycle':
            queryset = queryset.filter(is_deleted=True)
        elif self.action not in {'restore', 'recycle_action', 'purge', 'acl', 'references'}:
            queryset = queryset.filter(is_deleted=False)
        from .access import file_queryset_for_actor
        access = FileAccessGrant.MANAGE if self.action in {'recycle', 'restore', 'recycle_action', 'purge', 'acl'} else FileAccessGrant.READ
        from .library import with_organization
        return with_organization(file_queryset_for_actor(queryset, self.request.user, access=access), self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return FileUploadSerializer
        return FileSerializer

    def update(self, request, *args, **kwargs):
        return Response({'code': 405, 'message': '文件元数据为只读', 'data': None}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def partial_update(self, request, *args, **kwargs):
        return Response({'code': 405, 'message': '文件元数据为只读', 'data': None}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @extend_schema(responses=envelope('FileReferenceStatusResponse', FileReferenceStatusSerializer()))
    @action(detail=True, methods=['get'])
    def references(self, request, pk=None):
        from .references import is_referenced
        from apps.core.query_budget import query_budget
        instance = self.get_object()
        with query_budget():
            protected = is_referenced(instance)
        response = Response({'code': 200, 'message': 'success', 'data': {
            'protected': protected, 'lifecycle_version': instance.lifecycle_version,
        }})
        response['Cache-Control'] = 'private, no-store'
        return response

    @extend_schema(responses={(200, 'image/png'): OpenApiTypes.BINARY,
                              (200, 'application/pdf'): OpenApiTypes.BINARY,
                              413: MessageResponse, 415: MessageResponse, 422: MessageResponse})
    @action(detail=True, methods=['get'])
    @transaction.atomic
    def preview(self, request, pk=None):
        from .preview import preview_content
        authorize_write(request, 'file:download')
        instance = self._locked_file(pk)
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
            ip_address=request_ip(self.request),
        )

    @extend_schema(responses=envelope('ImageProcessingConfigResponse', ImageProcessingConfigSerializer()))
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, HasPermission])
    def processing_config(self, request):
        from .image_processing import processing_config
        response = Response({'code': 200, 'message': 'success', 'data': processing_config()})
        response['Cache-Control'] = 'private, no-store'
        return response

    @extend_schema(request=ImageTransformSerializer, responses={
        (200, 'image/png'): OpenApiTypes.BINARY, (200, 'image/jpeg'): OpenApiTypes.BINARY,
        (200, 'image/webp'): OpenApiTypes.BINARY, 409: MessageResponse,
        413: MessageResponse, 415: MessageResponse, 422: MessageResponse})
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, HasPermission])
    def transform(self, request, pk=None):
        from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, NotFound
        from apps.auth_app.sessions import locked_request_session
        from apps.core.modules import module_enabled
        from apps.logs.audit import write_audit
        from .image_processing import transform_content
        if not settings.ADMINCORE_IMAGE_PROCESSING_ENABLED:
            raise NotFound()
        serializer = ImageTransformSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            # 用户 → 原设备 → 文件。锁等待后使用新身份、范围和版本，不能沿用 get_object 的旧快照。
            actor = get_user_model().objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
            if actor is None:
                raise AuthenticationFailed('登录凭据已撤销')
            if request.auth is not None:
                locked_request_session(request, actor)
            if (actor.must_change_password or not has_permission_code(actor, 'file:process')
                    or not has_permission_code(actor, 'file:download')):
                raise PermissionDenied('没有操作权限')
            if not settings.ADMINCORE_IMAGE_PROCESSING_ENABLED or not module_enabled('files'):
                raise NotFound()
            from .access import file_queryset_for_actor
            queryset = file_queryset_for_actor(FileModel.objects.filter(purpose='general', is_deleted=False), actor, derivative=True)
            try:
                instance = queryset.select_for_update().filter(pk=pk).first()
            except DjangoValidationError as exc:
                raise NotFound() from exc
            if instance is None:
                raise NotFound()
            try:
                instance.check_lifecycle_version(serializer.validated_data['lifecycle_version'])
            except LifecycleConflict as exc:
                raise APIError(str(exc), status_code=409) from exc
            content, content_type, projection = transform_content(instance, serializer.validated_data)
            if request.auth is not None:
                locked_request_session(request, actor)
            # 角色/范围可独立更新；编码后、审计和公开结果前再读一次授权。
            if not all(has_permission_code(actor, code) for code in ('file:process', 'file:download')):
                raise PermissionDenied('没有操作权限')
            if not file_queryset_for_actor(FileModel.objects.filter(pk=instance.pk, purpose='general', is_deleted=False), actor, derivative=True).exists():
                raise NotFound()
            if not settings.ADMINCORE_IMAGE_PROCESSING_ENABLED or not module_enabled('files'):
                raise NotFound()
            write_audit(request=request, actor=actor, resource='file_transform', identifier=instance.pk,
                        action='download', after=projection)
        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="processed.{serializer.validated_data["format"]}"'
        response['Content-Length'] = str(len(content))
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "sandbox; default-src 'none'; frame-ancestors 'none'"
        response['X-Frame-Options'] = 'DENY'
        return response

    def create(self, request, *args, **kwargs):
        """上传文件后返回完整的文件信息（上传序列化器仅接收写入字段）"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        data = FileSerializer(serializer.instance, context=self.get_serializer_context()).data
        # 旧 v1 客户端仍读取顶层文件字段；迁移期保留，规范调用统一读取 data。
        return Response(
            {**data, 'code': 201, 'message': '上传成功', 'data': data},
            status=status.HTTP_201_CREATED,
        )

    def perform_create(self, serializer):
        from .serializers import cleanup_failed_upload
        file_obj = None
        try:
            with transaction.atomic():
                # 已登记的上传权限必须在存储和业务写入前执行。
                authorize_write(self.request, 'file:upload')
                file_obj = serializer.save()
                self._log('upload', file_obj, f'Uploaded file {file_obj.original_name}')
        except Exception:
            # 数据库回滚不回滚对象存储；只补偿本次新生成的键。
            if file_obj is not None:
                cleanup_failed_upload(file_obj)
            raise

    def _locked_file(self, identifier):
        """调用者已在 atomic 内授权用户，锁后重新计算目标范围。"""
        try:
            row = self.get_queryset().select_for_update(of=('self',)).filter(pk=identifier).first()
        except DjangoValidationError as exc:
            raise APIError('文件不存在', status_code=404) from exc
        if row is None or not self.get_queryset().filter(pk=row.pk).exists():
            raise APIError('文件不存在', status_code=404)
        return row

    def perform_destroy(self, instance):
        with transaction.atomic():
            authorize_write(self.request)
            instance = self._locked_file(instance.pk)
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
        from apps.logs.audit import write_audit
        write_audit(request=self.request, resource='file', identifier=instance.pk,
                    action='update' if operation == 'restore' else 'delete', before=before,
                    after=None if operation == 'purge' else self._snapshot(instance), description=json.dumps({
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

    @extend_schema(request=FileACLSerializer, responses=envelope('FileACLResponse', FileACLSerializer()))
    @action(detail=True, methods=['get', 'put'], url_path='acl')
    def acl(self, request, pk=None):
        """读取或替换单个文件的用户/角色授权。文件所有者和管理员可管理。"""
        from apps.auth_app.write_authorization import authorize_write
        from apps.permissions.models import Role
        from apps.auth_app.models import User
        from rest_framework.exceptions import PermissionDenied
        with transaction.atomic():
            if request.method.lower() == 'put':
                authorize_write(request, 'file:upload')
            instance = self._locked_file(pk)
            owner = request.user.is_staff or request.user.is_superuser or instance.uploader_id == request.user.pk
            delegated_read = request.method.lower() == 'get' and instance.access_grants.filter(
                is_active=True, access_level=FileAccessGrant.MANAGE).filter(
                    Q(user=request.user) | Q(role__userrole__user=request.user, role__is_active=True)).exists()
            if not (owner or delegated_read):
                raise PermissionDenied('只有文件所有者或管理员可以管理授权')
            if request.method.lower() == 'get':
                grants = instance.access_grants.filter(is_active=True).select_related('user', 'role')
                return Response({'code': 200, 'message': 'success', 'data': {'grants': [
                    {'user_id': str(item.user_id) if item.user_id else None,
                     'role_id': str(item.role_id) if item.role_id else None,
                     'access_level': item.access_level,
                     'inherit_to_derivatives': item.inherit_to_derivatives}
                    for item in grants]}})
            serializer = FileACLSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            grants = serializer.validated_data['grants']
            user_ids = [item['user_id'] for item in grants if item.get('user_id')]
            role_ids = [item['role_id'] for item in grants if item.get('role_id')]
            if User.objects.filter(pk__in=user_ids, is_active=True).count() != len(user_ids):
                raise serializers.ValidationError('授权用户不存在或已禁用')
            if Role.objects.filter(pk__in=role_ids, is_active=True).count() != len(role_ids):
                raise serializers.ValidationError('授权角色不存在或已禁用')
            instance.access_grants.all().delete()
            FileAccessGrant.objects.bulk_create([
                FileAccessGrant(file=instance, user_id=item.get('user_id'), role_id=item.get('role_id'),
                                access_level=item['access_level'],
                                inherit_to_derivatives=item['inherit_to_derivatives'])
                for item in grants])
            from apps.logs.audit import write_audit
            write_audit(request=request, actor=request.user, resource='file', identifier=instance.pk,
                        action='update', description=json.dumps({'operation': 'acl', 'grant_count': len(grants)}, ensure_ascii=False))
            return Response({'code': 200, 'message': '授权已更新', 'data': {'grants': grants}})

    @extend_schema(request=RestoreSerializer, responses=envelope('FileRestoreResponse', FileSerializer()))
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, HasPermission])
    def restore(self, request, pk=None):
        serializer = RestoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            authorize_write(request, 'file:restore')
            instance = self._locked_file(pk)
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
                    authorize_write(request, 'file:' + operation)
                    instance = self._locked_file(item['id'])
                    instance.check_lifecycle_version(item['lifecycle_version'])
                    if not instance.is_deleted:
                        raise LifecycleConflict('文件不在回收站，请刷新后重试')
                    if data['dry_run']:
                        if operation == 'purge':
                            from .references import assert_not_referenced
                            assert_not_referenced(instance)
                    elif operation == 'restore':
                        before = self._snapshot(instance)
                        instance.restore(item['lifecycle_version'])
                        self._lifecycle_log(instance, 'restore', before)
                    else:
                        instance.hard_delete(expected_version=item['lifecycle_version'], audit=lambda row: self._lifecycle_log(row, 'purge', self._snapshot(row)))
                    queued = operation == 'purge' and not data['dry_run']
                    result.update(status=202 if queued else 200,
                                  message='已登记删除，存储清理失败将自动重试' if queued else ('可执行' if data['dry_run'] else '已完成'),
                                  original_name=instance.original_name, size=instance.size)
            except LifecycleConflict as exc:
                result.update(status=409, message=str(exc))
            except APIException as exc:
                result.update(status=exc.status_code, message=str(exc.detail))
            except OSError:
                # 外部存储错误不泄露服务器路径、签名或凭据；记录和失败项可重试。
                result.update(status=503, message='存储暂时不可用，请稍后重试')
            results.append(result)
        succeeded = sum(item['status'] in (200, 202) for item in results)
        if not data['dry_run']:
            from apps.logs.audit import write_audit
            write_audit(request=request, action='other', resource='file', results=results,
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
    @transaction.atomic
    def download(self, request, pk=None):
        """下载文件（记录下载次数）"""
        authorize_write(request, 'file:download')
        file_obj = self._locked_file(pk)
        if not file_obj.file or not file_obj.file.storage.exists(file_obj.file.name):
            return Response({'code': 404, 'message': '文件不存在', 'data': None}, status=status.HTTP_404_NOT_FOUND)

        FileModel.objects.filter(id=file_obj.id).update(download_count=F('download_count') + 1)
        self._log('download', file_obj, f'Downloaded file {file_obj.original_name}')

        response = FileResponse(file_obj.file.open('rb'), as_attachment=True, filename=file_obj.original_name)
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response

    @action(detail=True, methods=['delete'], permission_classes=[IsAuthenticated, IsAdmin])
    @transaction.atomic
    def purge(self, request, pk=None):
        """物理删除文件：用户/设备先于文件锁，锁内重新判断权限和范围。"""
        authorize_write(request, 'file:purge', admin=True)
        file_obj = self._locked_file(pk)
        try:
            file_obj.hard_delete(expected_version=file_obj.lifecycle_version,
                                 audit=lambda row: self._lifecycle_log(row, 'purge', self._snapshot(row)))
        except LifecycleConflict as exc:
            raise APIError(str(exc), status_code=409) from exc
        except OSError as exc:
            raise APIError('存储暂时不可用，请稍后重试', status_code=503) from exc
        return Response({'code': 202, 'message': '已登记删除，存储清理失败将自动重试', 'data': None}, status=202)
