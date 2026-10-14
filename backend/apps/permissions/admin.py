"""
权限系统管理后台
"""

from django.contrib import admin
from .models import Role, Permission, Menu, UserRole, RolePermission
from apps.logs.admin_audit import AuditedAdminMixin


@admin.register(Permission)
class PermissionAdmin(AuditedAdminMixin, admin.ModelAdmin):
    """权限管理"""
    audit_resource = 'permission'
    list_display = ('code', 'name', 'resource', 'action', 'created_at')
    search_fields = ('code', 'name')
    list_filter = ('resource', 'action')


class RolePermissionInline(admin.TabularInline):
    """角色权限内联（角色权限通过 RolePermission 中间表维护）"""
    model = RolePermission
    extra = 1


@admin.register(Role)
class RoleAdmin(AuditedAdminMixin, admin.ModelAdmin):
    """角色管理"""
    audit_resource = 'role'
    list_display = ('name', 'is_active', 'created_at')
    search_fields = ('name',)
    inlines = (RolePermissionInline,)


@admin.register(UserRole)
class UserRoleAdmin(AuditedAdminMixin, admin.ModelAdmin):
    """用户角色管理"""
    audit_resource = 'user_role'
    list_display = ('user', 'role', 'created_at')
    search_fields = ('user__username', 'role__name')
    list_filter = ('role',)


@admin.register(Menu)
class MenuAdmin(AuditedAdminMixin, admin.ModelAdmin):
    """菜单管理"""
    audit_resource = 'menu'
    list_display = ('name', 'path', 'parent', 'order', 'is_visible', 'created_at')
    search_fields = ('name', 'path')
    list_filter = ('is_visible', 'parent')
    ordering = ('parent', 'order')
