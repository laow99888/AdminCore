"""
文件管理视图
"""

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiTypes
from apps.core.schema import MessageResponse

from django.core.files.storage import default_storage
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.logs.models import OperationLog
from apps.permissions.permissions import IsAdmin

from .models import FileModel
from .serializers import FileSerializer, FileUploadSerializer


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

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return FileModel.objects.none()
        queryset = FileModel.objects.filter(is_deleted=False).select_related('uploader')
        # 非管理员只能看到自己上传的文件
        from apps.core.data_scope import scope_queryset
        return scope_queryset(queryset, self.request.user, 'file', 'uploader_id', fallback='self')

    def get_serializer_class(self):
        if self.action == 'create':
            return FileUploadSerializer
        return FileSerializer

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
        instance.soft_delete()
        self._log('delete', instance, f'Deleted file {instance.original_name}')

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """下载文件（记录下载次数）"""
        file_obj = self.get_object()
        if not file_obj.file or not default_storage.exists(file_obj.file.name):
            return Response({'code': 404, 'message': '文件不存在', 'data': None}, status=status.HTTP_404_NOT_FOUND)

        FileModel.objects.filter(id=file_obj.id).update(download_count=file_obj.download_count + 1)
        self._log('download', file_obj, f'Downloaded file {file_obj.original_name}')

        response = FileResponse(file_obj.file.open('rb'), as_attachment=True, filename=file_obj.original_name)
        return response

    @action(detail=True, methods=['delete'], permission_classes=[IsAuthenticated, IsAdmin])
    def purge(self, request, pk=None):
        """物理删除文件（仅管理员）"""
        file_obj = FileModel.objects.filter(pk=pk).first()
        if not file_obj:
            return Response({'code': 404, 'message': '文件不存在', 'data': None}, status=status.HTTP_404_NOT_FOUND)
        name = file_obj.original_name
        file_obj.hard_delete()
        self._log('delete', file_obj, f'Purged file {name}')
        return Response({'code': 200, 'message': '文件已彻底删除', 'data': None})
