from django.contrib import admin

from apps.permissions.permissions import has_permission_code
from .models import OperationLog, LoginLog, ExceptionLog


class ReadOnlyLogAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        from apps.core.data_scope import scope_queryset
        return scope_queryset(super().get_queryset(request), request.user, 'log', 'user_id')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and has_permission_code(request.user, 'log:read')


@admin.register(OperationLog)
class OperationLogAdmin(ReadOnlyLogAdmin):
    list_display = ('created_at', 'action', 'resource', 'actor_identifier', 'request_id')
    fields = ('id', 'created_at', 'user', 'actor_identifier', 'action', 'resource', 'resource_id',
              'description', 'status', 'request_id', 'task_id', 'task_record_id', 'audit_version',
              'before_values', 'after_values', 'batch_results')
    readonly_fields = fields
    search_fields = ('request_id', 'resource_id')


@admin.register(LoginLog)
class LoginLogAdmin(ReadOnlyLogAdmin):
    fields = ('id', 'created_at', 'username', 'status', 'ip_address', 'error_message')
    readonly_fields = fields


@admin.register(ExceptionLog)
class ExceptionLogAdmin(ReadOnlyLogAdmin):
    fields = ('id', 'created_at', 'level', 'message', 'user', 'request_path', 'request_method')
    readonly_fields = fields
