"""
数据导入导出序列化器
"""

from rest_framework import serializers

from .resources import IMPORT_EXPORT_RESOURCES


class DataImportSerializer(serializers.Serializer):
    """数据导入请求"""
    file = serializers.FileField()
    resource = serializers.ChoiceField(choices=[(k, v['label']) for k, v in IMPORT_EXPORT_RESOURCES.items() if v['importable']])

    def validate_file(self, uploaded):
        from django.conf import settings
        if uploaded.size > min(settings.FILE_UPLOAD_MAX_SIZE, 10 * 1024 * 1024):
            raise serializers.ValidationError('导入文件超过上传大小限制')
        return uploaded


class DataExportSerializer(serializers.Serializer):
    resource = serializers.ChoiceField(choices=list(IMPORT_EXPORT_RESOURCES), default='users')
    export_format = serializers.ChoiceField(choices=['csv', 'xlsx'], default='csv')

    def to_internal_value(self, data):
        from apps.logs.models import OperationLog, LoginLog, ExceptionLog
        resource = data.get('resource', 'users')
        kind = data.get('log_type', 'operation')
        self.fields['search'] = serializers.CharField(required=False, max_length=200, allow_blank=True)
        if resource in {'users', 'roles', 'posts'}:
            self.fields['is_active'] = serializers.ChoiceField(choices=['true', 'false'], required=False)
        elif resource == 'files':
            self.fields['file_type'] = serializers.RegexField(r'^[a-zA-Z0-9]{1,20}$', required=False)
        elif resource == 'logs':
            self.fields['log_type'] = serializers.ChoiceField(choices=['operation', 'login', 'exception'], default='operation')
            if kind == 'operation':
                self.fields['action'] = serializers.ChoiceField(choices=[item[0] for item in OperationLog.ACTION_CHOICES], required=False)
                self.fields['resource_name'] = serializers.CharField(required=False, max_length=100)
            elif kind == 'login':
                self.fields['status'] = serializers.ChoiceField(choices=[item[0] for item in LoginLog.STATUS_CHOICES], required=False)
                self.fields['username'] = serializers.CharField(required=False, max_length=100)
            elif kind == 'exception':
                self.fields['level'] = serializers.ChoiceField(choices=[item[0] for item in ExceptionLog.LEVEL_CHOICES], required=False)
                self.fields['request_method'] = serializers.ChoiceField(choices=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'], required=False)
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({'filters': '存在不支持的筛选参数'})
        if hasattr(data, 'getlist') and any(len(data.getlist(key)) != 1 for key in data):
            raise serializers.ValidationError({'filters': '筛选参数不能重复'})
        values = super().to_internal_value(data)
        if 'is_active' in values:
            values['is_active'] = values['is_active'] == 'true'
        return values


class DataResourceSerializer(serializers.Serializer):
    resource = serializers.CharField()
    label = serializers.CharField()
    importable = serializers.BooleanField()
    exportable = serializers.BooleanField()
    business = serializers.BooleanField(required=False)


class DataResourceDirectorySerializer(serializers.Serializer):
    resources = DataResourceSerializer(many=True)
    max_rows = serializers.IntegerField()
    max_bytes = serializers.IntegerField()
