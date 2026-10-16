from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import OnlineForm, OnlineFormRecord
from .validators import validate_definition, validate_record


class OnlineFormSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    published_by_name = serializers.CharField(source='published_by.username', read_only=True, default=None)
    class Meta:
        model = OnlineForm
        fields = ['id', 'name', 'code', 'status', 'version', 'definition', 'created_by', 'created_by_name', 'published_by', 'published_by_name', 'published_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'status', 'version', 'created_by', 'created_by_name', 'published_by', 'published_by_name', 'published_at', 'created_at', 'updated_at']


class OnlineFormDesignSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnlineForm
        fields = ['id', 'name', 'code', 'status', 'version', 'definition']
        read_only_fields = ['id', 'status', 'version']
    def validate_definition(self, value):
        return validate_definition(value)
    def validate_code(self, value):
        if self.instance and self.instance.code == value:
            return value
        if OnlineForm.objects.filter(code=value).exists():
            raise serializers.ValidationError('表单编码已存在')
        if not isinstance(value, str) or not __import__('re').fullmatch(r'[a-z][a-z0-9-]{1,63}', value):
            raise serializers.ValidationError('表单编码必须为小写字母、数字和短横线')
        return value


class OnlineFormRecordSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.username', read_only=True)
    class Meta:
        model = OnlineFormRecord
        fields = ['id', 'form', 'form_version', 'owner', 'owner_name', 'data', 'version', 'created_at', 'updated_at']
        read_only_fields = ['id', 'form', 'form_version', 'owner', 'owner_name', 'version', 'created_at', 'updated_at']
