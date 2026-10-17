"""
用户管理 Django Admin
"""

from django.contrib import admin
from .models import UserProfile
from apps.core.sensitive import mask_phone
from apps.logs.admin_audit import AuditedAdminMixin


@admin.register(UserProfile)
class UserProfileAdmin(AuditedAdminMixin, admin.ModelAdmin):
    """用户资料管理"""
    audit_resource = 'user_profile'
    list_display = ('user', 'department', 'position', 'created_at')
    search_fields = ('user__username', 'department', 'position')
    list_filter = ('department',)
    exclude = ('phone',)
    readonly_fields = ('masked_phone',)

    @admin.display(description='手机号（原值请在系统用户管理查看）')
    def masked_phone(self, obj):
        return mask_phone(obj.user.phone)
