"""
用户管理 Django Admin
"""

from django.contrib import admin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """用户资料管理"""
    list_display = ('user', 'department', 'position', 'created_at')
    search_fields = ('user__username', 'department', 'position')
    list_filter = ('department',)
