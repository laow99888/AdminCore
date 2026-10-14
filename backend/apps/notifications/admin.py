"""
通知系统后台配置
"""

from django.contrib import admin

from .models import Notification
from apps.logs.admin_audit import AuditedAdminMixin


@admin.register(Notification)
class NotificationAdmin(AuditedAdminMixin, admin.ModelAdmin):
    audit_resource = 'notification'
    audit_module = 'notifications'
    list_display = ['title', 'recipient', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['title', 'content', 'recipient__username']
    readonly_fields = ['read_at', 'created_at', 'updated_at']
