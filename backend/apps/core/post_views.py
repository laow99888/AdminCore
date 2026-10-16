from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth_app.write_authorization import authorize_write
from apps.permissions.permissions import HasPermission, IsAdmin
from apps.permissions.field_permissions import enforce_write_fields, filter_read_fields
from .mixins import EnvelopeResponseMixin
from .models import Post, UserPost
from .personnel import PeoplePageSerializer, people_response, picker_departments, PickerDepartmentsSerializer, PeopleQuerySerializer
from .schema import envelope, MessageResponse
from .system_views import VersionConflict, audit


class StrictWriteSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise ValidationError({'non_field_errors': '请求必须为对象'})
        unknown = set(data) - {key for key, field in self.fields.items() if not field.read_only}
        if unknown:
            raise ValidationError({key: '不允许写入此字段' for key in sorted(unknown)})
        return super().to_internal_value(data)


class PostSerializer(StrictWriteSerializer):
    code = serializers.RegexField(r'^[a-z][a-z0-9_]{0,63}$', max_length=64)
    version = serializers.IntegerField(min_value=0)

    class Meta:
        model = Post
        fields = ['id', 'code', 'name', 'description', 'order', 'is_active', 'version']

    def validate(self, attrs):
        request = self.context.get('request')
        if request:
            enforce_write_fields(request.user, 'post', set(self.initial_data), allow=('version',))
        return super().validate(attrs)

    def to_representation(self, instance):
        request = self.context.get('request')
        return filter_read_fields(request.user if request else None, 'post', super().to_representation(instance))

    def validate_code(self, value):
        if self.instance and self.instance.code != value:
            raise serializers.ValidationError('岗位编码创建后不可修改')
        if Post.objects.filter(code=value).exclude(pk=self.instance.pk if self.instance else None).exists():
            raise serializers.ValidationError('岗位编码已存在')
        return value


class UserPostSerializer(StrictWriteSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    post_name = serializers.CharField(source='post.name', read_only=True)
    post_active = serializers.BooleanField(source='post.is_active', read_only=True)
    user_active = serializers.BooleanField(source='user.is_active', read_only=True)
    version = serializers.IntegerField(min_value=0)

    class Meta:
        model = UserPost
        fields = ['id', 'user', 'username', 'user_active', 'post', 'post_name', 'post_active', 'version']
        validators = []  # 数据库唯一约束负责并发，返回统一字段错误。


class DeleteVersionSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class PostPermissionMixin:
    permission_classes = [IsAuthenticated, IsAdmin, HasPermission]
    permission_map = {'list': 'post:read', 'retrieve': 'post:read', 'create': 'post:update',
                      'update': 'post:update', 'partial_update': 'post:update', 'destroy': 'post:update',
                      'choices': 'post:read'}

    def delete_version(self):
        serializer = DeleteVersionSerializer(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data['version']


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('PostDetailResponse', PostSerializer())),
    create=extend_schema(responses={201: envelope('PostCreatedResponse', PostSerializer())}),
    update=extend_schema(responses=envelope('PostUpdatedResponse', PostSerializer())),
    partial_update=extend_schema(responses=envelope('PostPatchedResponse', PostSerializer())),
    destroy=extend_schema(parameters=[OpenApiParameter('version', int, required=True)], responses=MessageResponse),
)
class PostViewSet(PostPermissionMixin, EnvelopeResponseMixin, viewsets.ModelViewSet):
    queryset = Post.objects.all()
    serializer_class = PostSerializer
    search_fields = ['code', 'name']
    filterset_fields = ['is_active']
    ordering_fields = ['order', 'name', 'code']
    ordering = ['order', 'name', 'id']

    @transaction.atomic
    def perform_create(self, serializer):
        authorize_write(self.request, 'post:update', admin=True)
        if serializer.validated_data['version'] != 0:
            raise ValidationError({'version': '新建岗位版本必须为 0'})
        try:
            with transaction.atomic():
                row = serializer.save(version=1)
        except IntegrityError as exc:
            raise ValidationError({'code': '岗位编码已存在'}) from exc
        audit(self.request, 'post', row.pk, None, PostSerializer(row).data)

    @transaction.atomic
    def perform_update(self, serializer):
        authorize_write(self.request, 'post:update', admin=True)
        row = get_object_or_404(Post.objects.select_for_update(), pk=serializer.instance.pk)
        if serializer.validated_data.get('version') != row.version:
            raise VersionConflict()
        serializer.instance = row
        if serializer.validated_data.get('code', row.code) != row.code:
            raise ValidationError({'code': '岗位编码创建后不可修改'})
        before = PostSerializer(row).data
        row = serializer.save(version=row.version + 1)
        audit(self.request, 'post', row.pk, before, PostSerializer(row).data)

    @transaction.atomic
    def perform_destroy(self, instance):
        authorize_write(self.request, 'post:update', admin=True)
        row = get_object_or_404(Post.objects.select_for_update(), pk=instance.pk)
        if self.delete_version() != row.version:
            raise VersionConflict()
        if row.assignments.exists():
            raise ValidationError({'post': '岗位仍有人任职，请先调整任职或停用岗位'})
        before, identifier = PostSerializer(row).data, row.pk
        row.delete()
        audit(self.request, 'post', identifier, before, None)

    @extend_schema(responses=envelope('PostChoicesResponse', PostSerializer(many=True)), filters=False)
    @action(detail=False, methods=['get'])
    def choices(self, request):
        rows = list(Post.objects.filter(is_active=True)[:1001])
        if len(rows) > 1000:
            raise ValidationError({'post': '启用岗位超过选择器上限，请按业务范围扩展选择器'})
        return Response({'code': 200, 'message': 'success', 'data': PostSerializer(rows, many=True).data})


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('UserPostDetailResponse', UserPostSerializer())),
    create=extend_schema(responses={201: envelope('UserPostCreatedResponse', UserPostSerializer())}),
    destroy=extend_schema(parameters=[OpenApiParameter('version', int, required=True)], responses=MessageResponse),
)
class UserPostViewSet(PostPermissionMixin, EnvelopeResponseMixin, viewsets.ModelViewSet):
    queryset = UserPost.objects.select_related('user', 'post').all()
    serializer_class = UserPostSerializer
    search_fields = ['user__username', 'post__name', 'post__code']
    filterset_fields = ['user', 'post']
    ordering_fields = ['created_at', 'user__username', 'post__code', 'post__order']
    ordering = ['user__username', 'post__order', 'id']
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    @transaction.atomic
    def perform_create(self, serializer):
        authorize_write(self.request, 'post:update', admin=True,
                        related_users=(serializer.validated_data['user'].pk,))
        if serializer.validated_data['version'] != 0:
            raise ValidationError({'version': '新建任职版本必须为 0'})
        # 用户（含操作者）按主键 -> 岗位 -> 任职，与其他写入口保持一致。
        post = get_object_or_404(Post.objects.select_for_update(), pk=serializer.validated_data['post'].pk)
        user = get_object_or_404(get_user_model(), pk=serializer.validated_data['user'].pk)
        if not post.is_active or not user.is_active:
            raise ValidationError({'post': '只能为启用账号分配启用岗位'})
        try:
            with transaction.atomic():
                row = serializer.save(version=1)
        except IntegrityError as exc:
            raise ValidationError({'post': '此人员已拥有该岗位'}) from exc
        audit(self.request, 'user_post', row.pk, None, UserPostSerializer(row).data)

    @transaction.atomic
    def perform_destroy(self, instance):
        authorize_write(self.request, 'post:update', admin=True, related_users=(instance.user_id,))
        get_object_or_404(Post.objects.select_for_update(), pk=instance.post_id)
        row = get_object_or_404(UserPost.objects.select_for_update(), pk=instance.pk)
        if self.delete_version() != row.version:
            raise VersionConflict()
        before, identifier = UserPostSerializer(row).data, row.pk
        row.delete()
        audit(self.request, 'user_post', identifier, before, None)


class PersonnelView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin, HasPermission]
    required_permission = 'post:read'

    @extend_schema(parameters=[PeopleQuerySerializer], responses=envelope('PersonnelPageResponse', PeoplePageSerializer()))
    def get(self, request):
        return people_response(request, self)


class PersonnelDepartmentsView(PersonnelView):
    @extend_schema(parameters=[], responses=envelope('PostPersonnelDepartmentsResponse', PickerDepartmentsSerializer()))
    def get(self, request):
        return Response({'code': 200, 'message': 'success', 'data': picker_departments(request.user)},
                        headers={'Cache-Control': 'private, no-store'})
