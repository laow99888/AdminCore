from apps.core.tenant_validation import TenantUniqueSerializerMixin
from rest_framework import serializers
from .models import ReportDefinition
from .dashboards import validate_design


class ReportSelectionSerializer(serializers.Serializer):
    widget = serializers.CharField()
    field = serializers.CharField()
    value = serializers.JSONField()


class ReportRunRequestSerializer(serializers.Serializer):
    filters = serializers.DictField(child=serializers.JSONField(), required=False)
    selection = ReportSelectionSerializer(required=False)


class ReportDetailsRequestSerializer(serializers.Serializer):
    widget = serializers.CharField(required=False, default='single')
    options = ReportRunRequestSerializer(required=False)
    group = serializers.DictField(child=serializers.JSONField(), required=False)
    page = serializers.IntegerField(min_value=1, max_value=100, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=20)


class ReportSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    published_by_name = serializers.CharField(source='published_by.username', read_only=True, default=None)

    class Meta:
        model = ReportDefinition
        fields = ['id', 'name', 'code', 'kind', 'status', 'version', 'definition', 'created_by', 'created_by_name', 'published_by', 'published_by_name', 'published_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'status', 'version', 'created_by', 'created_by_name', 'published_by', 'published_by_name', 'published_at', 'created_at', 'updated_at']


class ReportDesignSerializer(TenantUniqueSerializerMixin, serializers.ModelSerializer):
    tenant_unique_fields = ('code',)
    version = serializers.IntegerField(required=False, min_value=1)
    class Meta:
        model = ReportDefinition
        fields = ['id', 'name', 'code', 'kind', 'status', 'version', 'definition']
        read_only_fields = ['id', 'status']

    def validate_definition(self, value):
        return validate_design(value)

    def validate(self, attrs):
        definition = attrs.get('definition', self.instance.definition if self.instance else {})
        kind = attrs.get('kind', self.instance.kind if self.instance else 'report')
        if 'widgets' in definition and kind != 'dashboard':
            raise serializers.ValidationError('多组件定义必须使用大屏类型')
        return attrs

    def validate_code(self, value):
        import re
        if self.instance and self.instance.code == value:
            return value
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,63}', value):
            raise serializers.ValidationError('报表编码必须为小写字母、数字和短横线')
        if ReportDefinition.objects.filter(code=value).exists():
            raise serializers.ValidationError('报表编码已存在')
        return value
