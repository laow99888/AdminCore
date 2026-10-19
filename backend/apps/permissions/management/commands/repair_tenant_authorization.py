"""默认预览，只有显式 --apply 才恢复可由角色唯一确定归属的 NULL 关联。"""
import json

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Q

from apps.permissions.models import Role, RolePermission, UserRole


class Command(BaseCommand):
    help = '预览租户授权历史关联修复；--apply 将恢复既有授权的租户归属，请先备份并审核影响'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        result = {'applied': options['apply'], 'updated': {}, 'conflicts': {}}
        for model in (RolePermission, UserRole):
            name = model._meta.model_name
            query = model.all_objects.filter(tenant_id__isnull=True, role__tenant_id__isnull=False)
            # 锁定父角色，与正常角色更新同序；修复不创建或删除授权。
            role_ids = list(query.order_by('role_id').values_list('role_id', flat=True).distinct())
            list(Role.all_objects.select_for_update().filter(pk__in=role_ids).order_by('pk'))
            rows = list(query.select_for_update().select_related('role').order_by('pk'))
            result['updated'][name] = len(rows)
            result['conflicts'][name] = model.all_objects.filter(tenant_id__isnull=False).filter(
                Q(role__tenant_id__isnull=True) | ~Q(tenant_id=F('role__tenant_id'))).count()
            if options['apply']:
                for row in rows:
                    model.all_objects.filter(pk=row.pk, tenant_id__isnull=True).update(tenant_id=row.role.tenant_id)
        self.stdout.write(json.dumps(result, ensure_ascii=False))
