"""文件历史和逻辑容量入口。"""
from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.auth_app.write_authorization import authorize_write
from apps.core.exceptions import APIError
from apps.core.query_budget import query_budget
from apps.core.schema import envelope
from apps.core.tenancy import enabled
from apps.permissions.permissions import has_permission_code
from .capacity import capacity_data, capacity_scope, locked_capacity
from .library_serializers import StrictSerializer
from .library_views import success
from .versions import append_revision, history


class RevisionWriteSerializer(StrictSerializer):
    version = serializers.IntegerField(min_value=0)
    file_id = serializers.UUIDField(required=False)
    restore_number = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if ('file_id' in attrs) == ('restore_number' in attrs):
            raise serializers.ValidationError('新附件与回退版本必须且只能选择一个')
        return attrs


class RevisionSerializer(serializers.Serializer):
    number = serializers.IntegerField()
    file_id = serializers.UUIDField()
    original_name = serializers.CharField()
    size = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    restored_from = serializers.IntegerField(allow_null=True)


class HistorySerializer(serializers.Serializer):
    version = serializers.IntegerField()
    current_file = serializers.UUIDField()
    items = RevisionSerializer(many=True)
    has_more = serializers.BooleanField()


class StrictPageSerializer(StrictSerializer):
    page = serializers.IntegerField(min_value=1, max_value=1000, default=1)


class FileVersionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[StrictPageSerializer], responses=envelope('FileHistoryResponse', HistorySerializer()))
    def get(self, request, file_id):
        if not has_permission_code(request.user, 'file:read'):
            raise PermissionDenied()
        query = StrictPageSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        with query_budget():
            return success(history(request.user, file_id, query.validated_data['page']))

    @extend_schema(request=RevisionWriteSerializer, responses=envelope('FileRevisionCreatedResponse', HistorySerializer()))
    def post(self, request, file_id):
        serializer = RevisionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success(append_revision(request, file_id, serializer.validated_data))


class CapacitySerializer(serializers.Serializer):
    used_bytes = serializers.IntegerField()
    limit_bytes = serializers.IntegerField()
    remaining_bytes = serializers.IntegerField(allow_null=True)
    version = serializers.IntegerField()


class CapacityWriteSerializer(StrictSerializer):
    owner_id = serializers.UUIDField()
    limit_bytes = serializers.IntegerField(min_value=0, max_value=2 ** 53 - 1)
    version = serializers.IntegerField(min_value=0)


class CapacityQuerySerializer(StrictSerializer):
    owner_id = serializers.UUIDField(required=False)


def capacity_owner(request, owner_id):
    if str(owner_id) != str(request.user.pk) and not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied()
    owner = get_user_model().objects.filter(pk=owner_id, is_active=True).first()
    if enabled():
        from apps.core.models import TenantMembership
        if capacity_scope() is None:
            raise APIError('请先选择租户')
        if not TenantMembership.objects.filter(tenant_id=capacity_scope(), user_id=owner_id, is_active=True).exists():
            owner = None
    if owner is None:
        raise NotFound('用户不存在')
    return owner


class FileCapacityView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[CapacityQuerySerializer], responses=envelope('FileCapacityResponse', CapacitySerializer()))
    def get(self, request):
        if not has_permission_code(request.user, 'file:read'):
            raise PermissionDenied()
        serializer = CapacityQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        owner = capacity_owner(request, serializer.validated_data.get('owner_id', request.user.pk))
        return success(capacity_data(owner.pk, capacity_scope()))

    @extend_schema(request=CapacityWriteSerializer, responses=envelope('FileCapacityUpdatedResponse', CapacitySerializer()))
    @transaction.atomic
    def put(self, request):
        serializer = CapacityWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        actor = authorize_write(request, 'file:upload', admin=True, related_users=[values['owner_id']])
        tenant_id = capacity_scope()
        owner = capacity_owner(request, values['owner_id'])
        row = locked_capacity(owner.pk, tenant_id)
        expected = values['version']
        if row.version != expected:
            raise APIError('容量配置已变更，请刷新后重试', status_code=409)
        row.limit_bytes, row.version = values['limit_bytes'], row.version + 1
        row.save(update_fields=['limit_bytes', 'version', 'updated_at'])
        from apps.logs.audit import write_audit
        write_audit(request=request, actor=actor, resource='file_capacity', identifier=row.pk, action='update', after={
            'owner_id': str(owner.pk), 'limit_bytes': row.limit_bytes, 'version': row.version})
        return success(capacity_data(owner.pk, tenant_id, row))
