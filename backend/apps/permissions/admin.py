"""
权限系统管理后台
"""

from django.contrib import admin
from django import forms
from .models import Role, Permission, Menu, UserRole, RolePermission
from apps.logs.admin_audit import AuditedAdminMixin


class VersionedAdminForm(forms.ModelForm):
    edit_version = forms.IntegerField(required=False, widget=forms.HiddenInput)

    class Meta:
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance._state.adding:
            self.fields['edit_version'].initial = self.instance.version

    def clean(self):
        values = super().clean()
        if not self.instance._state.adding:
            current = type(self.instance).objects.filter(pk=self.instance.pk).values_list('version', flat=True).first()
            if values.get('edit_version') != current:
                raise forms.ValidationError('内容已被其他人修改，请刷新后重试')
            self.instance.version = current
        return values


class VersionedAdminMixin:
    form = VersionedAdminForm
    readonly_fields = ('version',)

    def save_model(self, request, obj, form, change):
        if change:
            obj.version += 1
        return super().save_model(request, obj, form, change)


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
class RoleAdmin(VersionedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
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
class MenuAdmin(VersionedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    """菜单管理"""
    audit_resource = 'menu'
    list_display = ('name', 'path', 'parent', 'order', 'is_visible', 'created_at')
    search_fields = ('name', 'path')
    list_filter = ('is_visible', 'parent')
    ordering = ('parent', 'order')
