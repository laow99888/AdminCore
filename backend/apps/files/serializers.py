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
            'download_count', 'created_at',
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
