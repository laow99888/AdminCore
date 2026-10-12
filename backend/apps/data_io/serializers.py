"""
数据导入导出序列化器
"""

from rest_framework import serializers

from .resources import IMPORT_EXPORT_RESOURCES


class DataImportSerializer(serializers.Serializer):
    """数据导入请求"""
    file = serializers.FileField()
    resource = serializers.ChoiceField(choices=[(k, v['label']) for k, v in IMPORT_EXPORT_RESOURCES.items()])

    def validate_file(self, uploaded):
        from django.conf import settings
        if uploaded.size > settings.FILE_UPLOAD_MAX_SIZE:
            raise serializers.ValidationError('导入文件超过上传大小限制')
        return uploaded
