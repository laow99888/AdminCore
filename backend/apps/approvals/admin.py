"""
审批流程后台配置
"""

from django.contrib import admin

from .models import ApprovalRequest


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ['title', 'request_type', 'applicant', 'assignee', 'status', 'decided_by', 'created_at']
    list_filter = ['status', 'request_type', 'created_at']
    search_fields = ['title', 'content', 'applicant__username', 'assignee__username']
    readonly_fields = ['decided_by', 'decided_at', 'created_at', 'updated_at']
