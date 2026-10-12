"""
用户管理序列化器
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import UserProfile

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):
    """用户资料序列化器"""
    class Meta:
        model = UserProfile
        fields = ('bio', 'phone', 'department', 'position')


class UserDetailSerializer(serializers.ModelSerializer):
    """用户详细序列化器"""
    profile = UserProfileSerializer(read_only=True)
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'avatar', 'phone',
                  'is_active', 'login_count', 'created_at', 'profile', 'roles')
        read_only_fields = ('id', 'created_at', 'login_count')

    def get_roles(self, obj):
        """获取用户角色"""
        from apps.permissions.models import UserRole
        roles = UserRole.objects.filter(user=obj).values('role__id', 'role__name')
        return list(roles)


class UserListSerializer(serializers.ModelSerializer):
    """用户列表序列化器"""
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'login_count', 'created_at')
        read_only_fields = ('id', 'created_at')


class UserCreateSerializer(serializers.ModelSerializer):
    """用户创建序列化器"""
    password = serializers.CharField(write_only=True, required=True, min_length=6)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'first_name', 'last_name', 'is_active')

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """用户修改序列化器"""
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'avatar', 'phone', 'is_active')


class BulkUserActionSerializer(serializers.Serializer):
    """批量用户操作序列化器"""
    user_ids = serializers.ListField(child=serializers.CharField(), required=True)
    action = serializers.ChoiceField(choices=['activate', 'deactivate', 'delete'], required=True)
