from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers
from .models import APICredential
from .policy import available_scopes


class CredentialSerializer(serializers.ModelSerializer):
    class Meta:
        model = APICredential
        fields = ('id', 'name', 'scopes', 'created_at', 'expires_at', 'revoked_at', 'last_used_at')
        read_only_fields = fields


class CredentialCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80, allow_blank=False)
    scopes = serializers.ListField(child=serializers.CharField(max_length=40), min_length=1, max_length=2)
    expires_at = serializers.DateTimeField()
    current_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=4096)

    def validate(self, values):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError('只能提交登记的开放凭证字段')
        if len(set(values['scopes'])) != len(values['scopes']) or not set(values['scopes']) <= set(available_scopes()):
            raise serializers.ValidationError({'scopes': '请选择已启用的只读能力'})
        now = timezone.now()
        if not now + timedelta(minutes=5) <= values['expires_at'] <= now + timedelta(days=90):
            raise serializers.ValidationError({'expires_at': '有效期必须为5分钟至90天'})
        return values


class CredentialIssuedSerializer(CredentialSerializer):
    token = serializers.CharField(read_only=True)

    class Meta(CredentialSerializer.Meta):
        fields = (*CredentialSerializer.Meta.fields, 'token')


class AvailableScopeSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
