"""Django 管理写入沿用显式投影；保存关联后审计，删除与审计同事务。"""
from contextlib import nullcontext

from django.db import transaction
from django.core.exceptions import PermissionDenied

from apps.core.modules import module_enabled
from .audit import snapshot, write_audit


class AuditedAdminMixin:
    audit_resource = ''
    audit_module = ''

    def available(self):
        return not self.audit_module or module_enabled(self.audit_module)

    def has_module_permission(self, request):
        return self.available() and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return self.available() and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return self.available() and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.available() and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self.available() and super().has_delete_permission(request, obj)

    def remember(self, request, obj):
        values = getattr(request, '_admin_audit_before', None)
        if values is None:
            values = request._admin_audit_before = {}
        key = (self.model._meta.label, str(obj.pk))
        if key not in values:
            row = self.model.objects.select_for_update().get(pk=obj.pk)
            values[key] = snapshot(self.audit_resource, row)

    def get_object(self, request, object_id, from_field=None):
        obj = super().get_object(request, object_id, from_field)
        if request.method == 'POST' and obj is not None and transaction.get_connection().in_atomic_block:
            self.remember(request, obj)
        return obj

    def save_model(self, request, obj, form, change):
        if change:
            self.remember(request, obj)
        return super().save_model(request, obj, form, change)

    def log_addition(self, request, obj, message):
        row = self.model.objects.get(pk=obj.pk)
        write_audit(request=request, resource=self.audit_resource, identifier=obj.pk, action='create',
                    after=snapshot(self.audit_resource, row), description='django_admin:create')
        return super().log_addition(request, obj, message)

    def log_change(self, request, obj, message):
        key = (self.model._meta.label, str(obj.pk))
        before = getattr(request, '_admin_audit_before', {})[key]
        row = self.model.objects.get(pk=obj.pk)
        write_audit(request=request, resource=self.audit_resource, identifier=obj.pk,
                    before=before, after=snapshot(self.audit_resource, row), description='django_admin:update')
        return super().log_change(request, obj, message)

    def log_deletions(self, request, queryset):
        identifiers = [obj.pk for obj in queryset]
        if len(identifiers) > 1000:
            raise PermissionDenied('后台批量删除最多 1000 项，请缩小选择范围')
        queryset = self.model.objects.select_for_update().filter(pk__in=identifiers).order_by('pk')
        if self.audit_resource == 'user':
            queryset = queryset.prefetch_related('roles', 'groups', 'user_permissions')
        elif self.audit_resource == 'role':
            queryset = queryset.prefetch_related('permissions')
        rows = list(queryset)
        for row in rows:
            write_audit(request=request, resource=self.audit_resource, identifier=row.pk, action='delete',
                        before=snapshot(self.audit_resource, row), description='django_admin:delete')
        if len(rows) > 1:
            write_audit(request=request, resource=self.audit_resource, action='delete', description='django_admin:batch_delete',
                        results=[{'id': row.pk, 'status': 200} for row in rows])
        return super().log_deletions(request, rows)

    def changelist_view(self, request, extra_context=None):
        # Django 原批量 action 未提供覆盖审计与删除的外层事务。
        with transaction.atomic() if request.method == 'POST' else nullcontext():
            return super().changelist_view(request, extra_context)
