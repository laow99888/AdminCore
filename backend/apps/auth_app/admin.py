"""
认证应用管理后台
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.db import transaction
from .models import User


class RequiredPasswordChangeForm(AdminPasswordChangeForm):
    @transaction.atomic
    def save(self, commit=True):
        self.user = User.objects.select_for_update().get(pk=self.user.pk)
        user = super().save(commit=False)
        user.must_change_password = True
        user.session_version += 1
        if commit:
            user.save()
        return user


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """用户管理后台"""
    change_password_form = RequiredPasswordChangeForm
    readonly_fields = ('must_change_password',)
    fieldsets = BaseUserAdmin.fieldsets + (
        ('额外信息', {'fields': ('avatar', 'phone', 'last_login_ip', 'login_count', 'must_change_password')}),
    )
    list_display = ('username', 'email', 'is_active', 'login_count', 'created_at')
    search_fields = ('username', 'email', 'phone')
    list_filter = ('is_active', 'created_at')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.must_change_password = True
        super().save_model(request, obj, form, change)
