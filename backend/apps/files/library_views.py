"""个人目录和标签 API。所有写入先串行锁用户，再锁文件。"""
import hashlib
import json

from django.db import transaction
from django.db.models import F
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth_app.write_authorization import authorize_write
from apps.core.exceptions import APIError
from apps.core.query_budget import query_budget
from apps.core.schema import MessageResponse, envelope
from apps.logs.audit import write_audit
from .library import (check_version, folder_for, organization_data, personal_rows,
                      validate_folder, visible_files)
from .library_serializers import (FileLibrarySerializer, FolderSerializer, FolderUpdateSerializer,
                                  FolderVersionSerializer, FolderWriteSerializer, OrganizationSerializer)
from .models import FileFolder, FileOrganization, FileOrganizationTag


def success(data, status=200):
    response = Response({'code': status, 'message': 'success', 'data': data}, status=status)
    response['Cache-Control'] = 'private, no-store'
    return response


def audit(request, resource, row, operation):
    # 个人目录名/标签可能含业务敏感内容；审计只记录结构标识与内容摘要。
    content = FolderSerializer(row).data if resource == 'file_folder' else organization_data(row)
    write_audit(request=request, resource=resource, identifier=row.pk, action='update', after={
        'id': str(row.pk), 'owner_id': str(request.user.pk), 'version': row.version,
        'operation': operation, 'content_sha256': hashlib.sha256(
            json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()})


class FileLibraryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=envelope('FileLibraryResponse', FileLibrarySerializer()))
    def get(self, request):
        with query_budget():
            folders = FolderSerializer(personal_rows(FileFolder, request.user).order_by('name', 'id'), many=True).data
            tags = list(FileOrganizationTag.objects.filter(
                organization__in=personal_rows(FileOrganization, request.user).filter(
                    file__in=visible_files(request.user))).order_by('name').values_list('name', flat=True).distinct()[:101])
        return success({'folders': folders, 'tags': tags[:100], 'tags_truncated': len(tags) > 100})


class FileFolderCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=FolderWriteSerializer, responses={201: envelope('FileFolderCreatedResponse', FolderSerializer())})
    @transaction.atomic
    def post(self, request):
        actor = authorize_write(request)
        serializer = FolderWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        parent = folder_for(actor, values['parent'])
        validate_folder(actor, values['name'], parent)
        row = FileFolder.objects.create(owner=actor, name=values['name'], parent=parent)
        audit(request, 'file_folder', row, 'create')
        return success(FolderSerializer(row).data, 201)


class FileFolderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=FolderUpdateSerializer, responses=envelope('FileFolderUpdatedResponse', FolderSerializer()))
    @transaction.atomic
    def put(self, request, folder_id):
        actor = authorize_write(request)
        serializer = FolderUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        row = folder_for(actor, folder_id)
        check_version(row, values['version'])
        parent = folder_for(actor, values['parent'])
        validate_folder(actor, values['name'], parent, row)
        row.name, row.parent, row.version = values['name'], parent, row.version + 1
        row.save(update_fields=['name', 'parent', 'version', 'updated_at'])
        audit(request, 'file_folder', row, 'update')
        return success(FolderSerializer(row).data)

    @extend_schema(request=FolderVersionSerializer, responses=MessageResponse)
    @transaction.atomic
    def delete(self, request, folder_id):
        actor = authorize_write(request)
        serializer = FolderVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = folder_for(actor, folder_id)
        check_version(row, serializer.validated_data['version'])
        if personal_rows(FileFolder, actor).filter(parent=row).exists():
            raise APIError('请先移动或删除子目录', status_code=409)
        # 只移除个人分类，文件本体、其他用户分类和 ACL 都不变。
        personal_rows(FileOrganization, actor).filter(folder=row).update(folder=None, version=F('version') + 1)
        audit(request, 'file_folder', row, 'delete')
        row.delete()
        return success(None)


class FileOrganizationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=OrganizationSerializer, responses=envelope('FileOrganizationResponse', OrganizationSerializer()))
    @transaction.atomic
    def put(self, request, file_id):
        actor = authorize_write(request)
        serializer = OrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        file = visible_files(actor).select_for_update().filter(pk=file_id).first()
        if file is None or not visible_files(actor).filter(pk=file_id).exists():
            raise NotFound('文件不存在')
        from apps.core.tenancy import current_tenant_id, enabled
        scope = current_tenant_id() if enabled() else None
        if str(file.tenant_id or '') != str(scope or ''):
            raise APIError('请先选择文件所属租户', status_code=400)
        folder = folder_for(actor, values['folder'])
        row = personal_rows(FileOrganization, actor).filter(file=file).first()
        check_version(row, values['version'])
        if row is None:
            row = FileOrganization.objects.create(file=file, owner=actor, folder=folder)
        else:
            row.folder, row.version = folder, row.version + 1
            row.save(update_fields=['folder', 'version', 'updated_at'])
        row.tags.all().delete()
        FileOrganizationTag.objects.bulk_create([FileOrganizationTag(
            organization=row, name=name, tenant_id=row.tenant_id) for name in values['tags']])
        audit(request, 'file_organization', row, 'update')
        return success(organization_data(row))
