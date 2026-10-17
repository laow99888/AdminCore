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
from apps.core.sensitive import MaskedContactSerializerMixin, phone_input_field
from apps.core.serializer_fields import TenantPrimaryKeyRelatedField
from apps.permissions.field_permissions import enforce_write_fields, filter_read_fields

User = get_user_model()


class UserProfileSerializer(MaskedContactSerializerMixin, serializers.ModelSerializer):
    """用户资料序列化器"""
    phone = serializers.CharField(source='user.phone', read_only=True)
    class Meta:
        model = UserProfile
        fields = ('bio', 'phone', 'department', 'position')


class UserDetailSerializer(MaskedContactSerializerMixin, serializers.ModelSerializer):
    """用户详细序列化器"""
    profile = UserProfileSerializer(read_only=True)
    roles = serializers.SerializerMethodField()
    version = serializers.IntegerField(source='profile_version', read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'avatar', 'phone',
                  'is_active', 'login_count', 'created_at', 'profile', 'roles', 'version')
        read_only_fields = ('id', 'created_at', 'login_count')

    def to_representation(self, instance):
        return filter_read_fields(self.context.get('request', None).user if self.context.get('request') else None,
                                  'user', super().to_representation(instance))

    def get_roles(self, obj) -> list[dict]:
        """获取用户角色"""
        from apps.permissions.models import UserRole
        roles = UserRole.objects.filter(user=obj).values('role__id', 'role__name')
        return list(roles)


class UserListSerializer(MaskedContactSerializerMixin, serializers.ModelSerializer):
    """用户列表序列化器"""
    version = serializers.IntegerField(source='profile_version', read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'phone', 'first_name', 'last_name', 'is_active', 'login_count', 'created_at', 'version')
        read_only_fields = ('id', 'created_at')

    def to_representation(self, instance):
        return filter_read_fields(self.context.get('request', None).user if self.context.get('request') else None,
                                  'user', super().to_representation(instance))


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


class UserCreateSerializer(MaskedContactSerializerMixin, UserRoleAssignmentMixin, serializers.ModelSerializer):
    """用户创建序列化器"""
    password = serializers.CharField(write_only=True, required=True)
    phone = phone_input_field()
    role_ids = TenantPrimaryKeyRelatedField(queryset=Role.objects.all(),
                                                  many=True, required=False, write_only=True, source='assigned_roles')

    class Meta:
        model = User
        fields = ('username', 'email', 'phone', 'password', 'first_name', 'last_name', 'is_active', 'role_ids', 'must_change_password')
        extra_kwargs = {'must_change_password': {'default': True}}

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        if request:
            enforce_write_fields(request.user, 'user', set(self.initial_data),
                                 allow=('password', 'role_ids', 'must_change_password'))
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


class UserUpdateSerializer(MaskedContactSerializerMixin, UserRoleAssignmentMixin, serializers.ModelSerializer):
    """用户修改序列化器"""
    phone = phone_input_field()
    # 兼容旧客户端提交的改密标志；该字段只读，不能通过用户编辑接口清除。
    must_change_password = serializers.BooleanField(read_only=True)
    version = serializers.IntegerField(source='profile_version', min_value=1, required=False, help_text='更新时必填：读取详情返回的 version；版本过期返回 409 且不写入。')
    role_ids = TenantPrimaryKeyRelatedField(queryset=Role.objects.all(),
                                                  many=True, required=False, write_only=True, source='assigned_roles')

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'avatar', 'phone', 'is_active', 'role_ids', 'version', 'must_change_password')
        read_only_fields = ('must_change_password',)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        if request:
            enforce_write_fields(request.user, 'user', set(self.initial_data), allow=('version', 'role_ids', 'must_change_password'))
        if 'profile_version' not in attrs:
            raise serializers.ValidationError({'version': '更新必须传入当前版本'})
        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = User.objects.select_for_update().get(pk=instance.pk)
        if validated_data.pop('profile_version') != instance.profile_version:
            from apps.core.system_views import VersionConflict
            raise VersionConflict()
        roles = validated_data.pop('assigned_roles', None)
        validated_data['profile_version'] = instance.profile_version + 1
        instance = super().update(instance, validated_data)
        self.save_roles(instance, roles)
        return instance


class BulkUserActionSerializer(serializers.Serializer):
    """批量用户操作序列化器"""
    user_ids = serializers.ListField(child=serializers.UUIDField(), required=True, min_length=1, max_length=1000)
    action = serializers.ChoiceField(choices=['activate', 'deactivate', 'delete'], required=True)


class BulkUserItemResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.IntegerField()


class BulkUserActionResultSerializer(serializers.Serializer):
    atomic = serializers.BooleanField()
    succeeded = serializers.IntegerField(min_value=0)
    failed = serializers.IntegerField(min_value=0)
    results = BulkUserItemResultSerializer(many=True)


class SensitiveContactRequestSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=4096)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - {'current_password'}:
            raise serializers.ValidationError({'non_field_errors': ['仅接受本次操作的当前密码']})
        return super().to_internal_value(data)


class SensitiveContactSerializer(serializers.Serializer):
    email = serializers.EmailField(allow_blank=True, read_only=True)
    phone = serializers.CharField(allow_blank=True, read_only=True)
