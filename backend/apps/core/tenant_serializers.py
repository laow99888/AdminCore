from rest_framework import serializers
from .models import Tenant, TenantMembership

class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ('id', 'slug', 'name', 'status', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

class TenantMembershipSerializer(serializers.ModelSerializer):
    def validate_user(self, value):
        if value.is_service_account:
            raise serializers.ValidationError('机器身份只能在独立管理入口维护')
        return value

    username = serializers.CharField(source='user.username', read_only=True)
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    class Meta:
        model = TenantMembership
        fields = ('id', 'tenant', 'tenant_name', 'user', 'username', 'role', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')
