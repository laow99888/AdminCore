"""
任务调度后台配置
"""

from django.contrib import admin

from .models import TaskRecord
from apps.logs.admin_audit import AuditedAdminMixin


@admin.register(TaskRecord)
class TaskRecordAdmin(AuditedAdminMixin, admin.ModelAdmin):
    audit_resource = 'task'
    audit_module = 'tasks'
    list_display = ['name', 'task_type', 'status', 'progress', 'creator', 'started_at', 'completed_at', 'created_at']
    list_filter = ['status', 'task_type', 'created_at']
    search_fields = ['name', 'related_resource', 'celery_task_id']
    readonly_fields = [f.name for f in TaskRecord._meta.fields]
