"""
文件管理序列化器
"""

import hashlib
import os
import logging
from collections.abc import Mapping

from django.conf import settings
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import FileModel, FileAccessGrant
from .library_serializers import OrganizationSerializer


class FileSerializer(serializers.ModelSerializer):
    """文件信息序列化（读取）"""
    uploader_name = serializers.CharField(source='uploader.username', read_only=True, default=None)
    file = serializers.SerializerMethodField()
    size_display = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()

    class Meta:
        model = FileModel
        fields = [
            'id', 'original_name', 'file', 'file_type', 'size', 'size_display',
            'content_type', 'md5', 'description', 'uploader', 'uploader_name',
            'download_count', 'created_at', 'is_deleted', 'deleted_at', 'deleted_by', 'lifecycle_version', 'organization',
        ]
        read_only_fields = fields

    def get_file(self, obj) -> str:
        from django.urls import reverse
        path = reverse('file-download', args=[obj.pk])
        request = self.context.get('request')
        return request.build_absolute_uri(path) if request else path

    @extend_schema_field(OrganizationSerializer)
    def get_organization(self, obj):
        from .library import organization_data
        rows = getattr(obj, 'personal_organization', [])
        return organization_data(rows[0] if rows else None)

    def get_size_display(self, obj) -> str:
        """人类可读的文件大小"""
        size = float(obj.size)
        for unit in ('B', 'KB', 'MB', 'GB'):
            if size < 1024:
                return f'{size:.0f} B' if unit == 'B' else f'{size:.1f} {unit}'
            size /= 1024
        return f'{size:.1f} TB'


class FileACLGrantSerializer(serializers.Serializer):
    user_id = serializers.UUIDField(required=False, allow_null=True)
    role_id = serializers.UUIDField(required=False, allow_null=True)
    access_level = serializers.ChoiceField(choices=FileAccessGrant.ACCESS_CHOICES)
    inherit_to_derivatives = serializers.BooleanField(default=True)

    def validate(self, attrs):
        if bool(attrs.get('user_id')) == bool(attrs.get('role_id')):
            raise serializers.ValidationError('user_id 与 role_id 必须且只能填写一个')
        return attrs


class FileACLSerializer(serializers.Serializer):
    grants = FileACLGrantSerializer(many=True, max_length=100)

    def validate_grants(self, value):
        principals = [(item.get('user_id'), item.get('role_id')) for item in value]
        if len(principals) != len(set(principals)):
            raise serializers.ValidationError('同一用户或角色不能重复授权')
        return value


class RestoreSerializer(serializers.Serializer):
    lifecycle_version = serializers.IntegerField(min_value=1)


class ImageProcessingConfigSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    max_bytes = serializers.IntegerField()
    max_pixels = serializers.IntegerField()
    max_dimension = serializers.IntegerField()
    watermark_max_bytes = serializers.IntegerField()
    formats = serializers.ListField(child=serializers.CharField())


class ImageTransformSerializer(RestoreSerializer):
    width = serializers.IntegerField(min_value=1, max_value=4096, default=1280)
    height = serializers.IntegerField(min_value=1, max_value=4096, default=1280)
    format = serializers.ChoiceField(choices=['png', 'jpeg', 'webp'], default='webp')
    quality = serializers.IntegerField(min_value=40, max_value=95, default=80)
    watermark = serializers.FileField(required=False)
    opacity = serializers.IntegerField(min_value=10, max_value=100, default=60)
    position = serializers.ChoiceField(choices=['bottom-right', 'center'], default='bottom-right')

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({'non_field_errors': ['处理参数必须是对象']})
        if set(data) - set(self.fields):
            raise serializers.ValidationError({'non_field_errors': ['存在未登记的处理参数']})
        if hasattr(data, 'getlist') and any(len(data.getlist(key)) != 1 for key in data):
            raise serializers.ValidationError({'non_field_errors': ['处理参数不能重复']})
        return super().to_internal_value(data)

    def validate_watermark(self, value):
        from .image_processing import MAX_WATERMARK_BYTES
        if value.size > MAX_WATERMARK_BYTES:
            raise serializers.ValidationError('水印图片最大 512 KiB')
        from .antivirus import checked_upload
        return checked_upload(value, stage='watermark_upload')


class RecyclePolicySerializer(serializers.Serializer):
    retention_days = serializers.IntegerField()
    cleanup_enabled = serializers.BooleanField()


class RecycleItemSerializer(RestoreSerializer):
    id = serializers.UUIDField()


class RecycleActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['restore', 'purge'])
    items = RecycleItemSerializer(many=True, allow_empty=False, max_length=100)
    dry_run = serializers.BooleanField(default=False)
    confirmation = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        ids = [item['id'] for item in attrs['items']]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError('不能重复选择同一文件')
        if attrs['action'] == 'restore' and attrs['dry_run']:
            raise serializers.ValidationError('恢复不支持删除影响预览')
        if attrs['action'] == 'purge' and not attrs['dry_run'] and attrs.get('confirmation') != 'DELETE':
            raise serializers.ValidationError('彻底删除必须输入 DELETE 确认')
        return attrs


class RecycleResultItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.IntegerField()
    message = serializers.CharField()
    original_name = serializers.CharField(required=False)
    size = serializers.IntegerField(required=False)


class RecycleResultSerializer(serializers.Serializer):
    results = RecycleResultItemSerializer(many=True)
    dry_run = serializers.BooleanField()
    succeeded = serializers.IntegerField()
    failed = serializers.IntegerField()


def cleanup_failed_upload(instance):
    """仅用于刚创建的上传对象；不接受客户端提供或历史记录中的存储键。"""
    if instance.file and instance.file._committed:
        try:
            instance.file.storage.delete(instance.file.name)
        except Exception:
            # 不记录存储地址或凭据；清理失败需由运维清点孤立上传对象。
            logging.getLogger(__name__).error('Failed to clean newly created upload after rollback')


class FileUploadSerializer(serializers.ModelSerializer):
    """文件上传序列化（校验白名单和大小限制）"""
    file = serializers.FileField(write_only=True)

    class Meta:
        model = FileModel
        fields = ['file', 'description']
        extra_kwargs = {
            'description': {'required': False, 'allow_blank': True},
        }

    def validate_file(self, value):
        from .upload_validation import validate_upload_metadata
        validate_upload_metadata(value.name, value.size)

        # 计算 MD5 用于去重比对
        md5 = hashlib.md5()
        for chunk in value.chunks():
            md5.update(chunk)
        value._md5 = md5.hexdigest()

        return value

    def create(self, validated_data):
        uploaded = validated_data.pop('file')
        request = self.context['request']
        instance = FileModel(
            original_name=os.path.basename(uploaded.name),
            file=uploaded,
            file_type=os.path.splitext(uploaded.name)[1].lower().lstrip('.'),
            size=uploaded.size,
            content_type=getattr(uploaded, 'content_type', '') or '',
            md5=getattr(uploaded, '_md5', ''),
            description=validated_data.get('description', ''),
            uploader=request.user if request.user.is_authenticated else None,
        )
        try:
            instance.save()
        except Exception:
            cleanup_failed_upload(instance)
            raise
        return instance
