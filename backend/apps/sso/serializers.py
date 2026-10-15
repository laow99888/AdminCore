import re

from rest_framework import serializers

from .models import ExternalIdentity


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({'non_field_errors': ['请求包含不允许的字段']})
        return super().to_internal_value(data)


class IdentitySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = ExternalIdentity
        fields = ('id', 'user_id', 'username', 'issuer', 'subject', 'created_at', 'revoked_at')
        read_only_fields = fields


class BindSerializer(StrictSerializer):
    user_id = serializers.UUIDField()
    subject = serializers.CharField(max_length=255, trim_whitespace=False)
    current_password = serializers.CharField(max_length=4096, write_only=True, trim_whitespace=False)

    def validate_subject(self, value):
        if not re.fullmatch(r'[\x21-\x7e]{1,255}', value):
            raise serializers.ValidationError('外部 subject 必须是供应商提供的区分大小写的 ASCII 标识')
        return value


class UnbindSerializer(StrictSerializer):
    current_password = serializers.CharField(max_length=4096, write_only=True, trim_whitespace=False)


class StartSerializer(StrictSerializer):
    captcha_id = serializers.UUIDField(required=False)
    captcha_code = serializers.CharField(max_length=5, required=False)


class CompleteSerializer(StartSerializer):
    otp_code = serializers.RegexField(r'^(?:[0-9]{6}|[0-9a-f]{32})$', max_length=32, required=False,
                                     write_only=True, trim_whitespace=False)


class ConfigSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    label = serializers.CharField(required=False)


class AuthorizationSerializer(serializers.Serializer):
    authorization_url = serializers.URLField()


class StatusSerializer(serializers.Serializer):
    ready = serializers.BooleanField()
    mfa_required = serializers.BooleanField()
    captcha = serializers.JSONField()


class SSOLoginUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    username = serializers.CharField()
    email = serializers.CharField(allow_blank=True)
    avatar = serializers.CharField(allow_blank=True)
    must_change_password = serializers.BooleanField()


class CompletedSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = SSOLoginUserSerializer()
