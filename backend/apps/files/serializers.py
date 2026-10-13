"""
文件管理序列化器
"""

import hashlib
import os

from django.conf import settings
from rest_framework import serializers

from .models import FileModel


class FileSerializer(serializers.ModelSerializer):
    """文件信息序列化（读取）"""
    uploader_name = serializers.CharField(source='uploader.username', read_only=True, default=None)
    file = serializers.SerializerMethodField()
    size_display = serializers.SerializerMethodField()

    class Meta:
        model = FileModel
        fields = [
            'id', 'original_name', 'file', 'file_type', 'size', 'size_display',
            'content_type', 'md5', 'description', 'uploader', 'uploader_name',
            'download_count', 'created_at', 'is_deleted', 'deleted_at', 'deleted_by', 'lifecycle_version',
        ]
        read_only_fields = fields

    def get_file(self, obj) -> str:
        from django.urls import reverse
        path = reverse('file-download', args=[obj.pk])
        request = self.context.get('request')
        return request.build_absolute_uri(path) if request else path

    def get_size_display(self, obj) -> str:
        """人类可读的文件大小"""
        size = float(obj.size)
        for unit in ('B', 'KB', 'MB', 'GB'):
            if size < 1024:
                return f'{size:.0f} B' if unit == 'B' else f'{size:.1f} {unit}'
            size /= 1024
        return f'{size:.1f} TB'


class RestoreSerializer(serializers.Serializer):
    lifecycle_version = serializers.IntegerField(min_value=1)


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
        ext = os.path.splitext(value.name)[1].lower().lstrip('.')
        allowed = [e.lower() for e in getattr(settings, 'FILE_UPLOAD_ALLOWED_EXTENSIONS', [])]
        max_size = getattr(settings, 'FILE_UPLOAD_MAX_SIZE', 50 * 1024 * 1024)

        if allowed and ext not in allowed:
            raise serializers.ValidationError(
                f'不支持的文件类型 ".{ext}"，允许的类型：{", ".join(allowed)}'
            )
        if value.size == 0:
            raise serializers.ValidationError('不允许上传空文件')
        if value.size > max_size:
            raise serializers.ValidationError(
                f'文件大小超出限制（最大 {max_size // (1024 * 1024)}MB）'
            )

        # 计算 MD5 用于去重比对
        md5 = hashlib.md5()
        for chunk in value.chunks():
            md5.update(chunk)
        value._md5 = md5.hexdigest()

        return value

    def create(self, validated_data):
        uploaded = validated_data.pop('file')
        request = self.context['request']
        return FileModel.objects.create(
            original_name=os.path.basename(uploaded.name),
            file=uploaded,
            file_type=os.path.splitext(uploaded.name)[1].lower().lstrip('.'),
            size=uploaded.size,
            content_type=getattr(uploaded, 'content_type', '') or '',
            md5=getattr(uploaded, '_md5', ''),
            description=validated_data.get('description', ''),
            uploader=request.user if request.user.is_authenticated else None,
        )
