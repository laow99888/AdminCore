from rest_framework import serializers
from .models import ReportDefinition
from .validators import validate_definition


class ReportSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    published_by_name = serializers.CharField(source='published_by.username', read_only=True, default=None)

    class Meta:
        model = ReportDefinition
        fields = ['id', 'name', 'code', 'kind', 'status', 'version', 'definition', 'created_by', 'created_by_name', 'published_by', 'published_by_name', 'published_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'status', 'version', 'created_by', 'created_by_name', 'published_by', 'published_by_name', 'published_at', 'created_at', 'updated_at']


class ReportDesignSerializer(serializers.ModelSerializer):
    version = serializers.IntegerField(required=False, min_value=1)
    class Meta:
        model = ReportDefinition
        fields = ['id', 'name', 'code', 'kind', 'status', 'version', 'definition']
        read_only_fields = ['id', 'status']

    def validate_definition(self, value):
        return validate_definition(value)

    def validate_code(self, value):
        import re
        if self.instance and self.instance.code == value:
            return value
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,63}', value):
            raise serializers.ValidationError('报表编码必须为小写字母、数字和短横线')
        if ReportDefinition.objects.filter(code=value).exists():
            raise serializers.ValidationError('报表编码已存在')
        return value
