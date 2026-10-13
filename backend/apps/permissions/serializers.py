"""
权限系统序列化器
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.helpers import lazy_serializer
from django.db import transaction
from .models import Role, Permission, Menu, UserRole


class PermissionSerializer(serializers.ModelSerializer):
    """权限序列化器"""
    class Meta:
        model = Permission
        fields = ('id', 'name', 'code', 'resource', 'action', 'description', 'created_at')
        read_only_fields = ('id', 'created_at')


class RolePermissionSerializer(serializers.ModelSerializer):
    """角色权限序列化器"""
    permission_detail = PermissionSerializer(source='permission', read_only=True)

    class Meta:
        model = Role
        fields = ('id', 'name', 'description', 'is_active', 'permissions')
        read_only_fields = ('id',)


class RoleSerializer(serializers.ModelSerializer):
    """角色序列化器"""
    # Role 与 Permission 通过 RolePermission 中间表关联，显式取权限明细
    permissions = serializers.SerializerMethodField()
    permission_ids = serializers.PrimaryKeyRelatedField(
        queryset=Permission.objects.all(),
        many=True,
        required=False,
        write_only=True,
        source='permission_objects',
    )

    class Meta:
        model = Role
        fields = ('id', 'name', 'description', 'is_active', 'permissions', 'permission_ids', 'created_at')
        read_only_fields = ('id', 'created_at')

    @extend_schema_field(PermissionSerializer(many=True))
    def get_permissions(self, role):
        return PermissionSerializer(
            Permission.objects.filter(rolepermission__role=role), many=True
        ).data

    def validate_permission_ids(self, permissions):
        if len({permission.pk for permission in permissions}) != len(permissions):
            raise serializers.ValidationError('权限不能重复')
        return permissions

    def _save_permissions(self, role, permission_objects):
        """重建角色-权限关联（RolePermission 显式中间表）"""
        from .models import RolePermission
        RolePermission.objects.filter(role=role).delete()
        RolePermission.objects.bulk_create(
            [RolePermission(role=role, permission=perm) for perm in permission_objects]
        )

    @transaction.atomic
    def create(self, validated_data):
        permission_objects = validated_data.pop('permission_objects', [])
        role = Role.objects.create(**validated_data)
        self._save_permissions(role, permission_objects)
        return role

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = Role.objects.select_for_update().get(pk=instance.pk)
        permission_objects = validated_data.pop('permission_objects', None)
        instance = super().update(instance, validated_data)
        if permission_objects is not None:
            self._save_permissions(instance, permission_objects)
        return instance


class MenuSerializer(serializers.ModelSerializer):
    """菜单序列化器"""
    children = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = ('id', 'name', 'path', 'icon', 'order', 'parent', 'permission', 'is_visible', 'children')

    def validate_path(self, value):
        if not value.startswith('/') or value.startswith('//') or any(char in value for char in ('?', '#', '\\')):
            raise serializers.ValidationError('请填写以 / 开头的站内路由路径')
        return value

    @extend_schema_field(lazy_serializer('apps.permissions.serializers.MenuSerializer')(many=True))
    def get_children(self, obj):
        """递归获取子菜单"""
        children = obj.children.all()
        if not self.context.get('manage_menus'):
            children = children.filter(is_visible=True)
            from apps.core.modules import path_enabled
            children = [child for child in children if path_enabled(child.path)]
        allowed_ids = self.context.get('allowed_menu_ids')
        if allowed_ids is not None:
            children = [child for child in children if child.id in allowed_ids]
        return MenuSerializer(children, many=True, context=self.context).data


class UserRoleSerializer(serializers.ModelSerializer):
    """用户角色序列化器"""
    role_detail = RoleSerializer(source='role', read_only=True)

    class Meta:
        model = UserRole
        fields = ('id', 'user', 'role', 'role_detail')
        read_only_fields = ('id',)
