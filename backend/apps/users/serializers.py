"""
用户管理序列化器
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.exceptions import PermissionDenied
from apps.permissions.models import Role, UserRole
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

    def get_roles(self, obj) -> list[dict]:
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


class UserRoleAssignmentMixin:
    """仅管理员可以赋予角色，避免用户管理权限变成提权入口。"""
    def validate(self, attrs):
        attrs = super().validate(attrs)
        roles = attrs.get('assigned_roles')
        if roles is not None:
            actor = self.context['request'].user
            if not (actor.is_staff or actor.is_superuser):
                raise PermissionDenied('只有管理员可以分配用户角色')
            if len({role.pk for role in roles}) != len(roles):
                raise serializers.ValidationError({'role_ids': '角色不能重复'})
            existing = set(UserRole.objects.filter(user=self.instance).values_list('role_id', flat=True)) if self.instance else set()
            if any(not role.is_active and role.pk not in existing for role in roles):
                raise serializers.ValidationError({'role_ids': '不能新增分配已禁用的角色'})
        return attrs

    def save_roles(self, user, roles):
        if roles is not None:
            UserRole.objects.filter(user=user).delete()
            UserRole.objects.bulk_create([UserRole(user=user, role=role) for role in roles])


class UserCreateSerializer(UserRoleAssignmentMixin, serializers.ModelSerializer):
    """用户创建序列化器"""
    password = serializers.CharField(write_only=True, required=True)
    role_ids = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all(),
                                                  many=True, required=False, write_only=True, source='assigned_roles')

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'first_name', 'last_name', 'is_active', 'role_ids')

    def validate(self, attrs):
        attrs = super().validate(attrs)
        candidate = User(**{key: value for key, value in attrs.items() if key not in ('password', 'assigned_roles')})
        try:
            validate_password(attrs['password'], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages}) from exc
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop('password')
        roles = validated_data.pop('assigned_roles', None)
        user = User.objects.create_user(password=password, **validated_data)
        self.save_roles(user, roles)
        return user


class UserUpdateSerializer(UserRoleAssignmentMixin, serializers.ModelSerializer):
    """用户修改序列化器"""
    role_ids = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all(),
                                                  many=True, required=False, write_only=True, source='assigned_roles')

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'avatar', 'phone', 'is_active', 'role_ids')

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = User.objects.select_for_update().get(pk=instance.pk)
        roles = validated_data.pop('assigned_roles', None)
        instance = super().update(instance, validated_data)
        self.save_roles(instance, roles)
        return instance


class BulkUserActionSerializer(serializers.Serializer):
    """批量用户操作序列化器"""
    user_ids = serializers.ListField(child=serializers.CharField(), required=True)
    action = serializers.ChoiceField(choices=['activate', 'deactivate', 'delete'], required=True)
