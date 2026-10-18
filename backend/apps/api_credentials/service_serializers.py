"""机器身份协议；普通用户 CRUD 无法管理这些主体。"""
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_serializer
from .models import ServiceIdentity
from .serializers import CredentialCreateSerializer


class StrictSerializer(serializers.Serializer):
    def validate(self, values):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError('只能提交登记字段')
        return values


@extend_schema_serializer(component_name='ServiceIdentity')
class IdentitySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source='user_id', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', read_only=True)
    role_ids = serializers.SerializerMethodField()

    def get_role_ids(self, row) -> list[str]:
        return [str(value) for value in row.user.roles.values_list('role_id', flat=True)]

    class Meta:
        model = ServiceIdentity
        fields = ('id', 'name', 'description', 'tenant_id', 'is_active', 'role_ids', 'version', 'created_at')
        read_only_fields = fields


class IdentityCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=80)
    description = serializers.CharField(max_length=300, allow_blank=True, required=False, default='')
    role_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=16)
    current_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=4096)


class IdentityUpdateSerializer(IdentityCreateSerializer):
    name = serializers.CharField(max_length=80, required=False)
    description = serializers.CharField(max_length=300, allow_blank=True, required=False)
    role_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=16, required=False)
    is_active = serializers.BooleanField(required=False)
    version = serializers.IntegerField(min_value=1)


class IdentityCredentialCreateSerializer(CredentialCreateSerializer):
    pass


class IdentityCredentialActionSerializer(StrictSerializer):
    credential_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)
    current_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=4096)


class IdentityRoleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
