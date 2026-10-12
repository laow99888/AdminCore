"""
认证应用管理后台
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """用户管理后台"""
    fieldsets = BaseUserAdmin.fieldsets + (
        ('额外信息', {'fields': ('avatar', 'phone', 'last_login_ip', 'login_count')}),
    )
    list_display = ('username', 'email', 'is_active', 'login_count', 'created_at')
    search_fields = ('username', 'email', 'phone')
    list_filter = ('is_active', 'created_at')
