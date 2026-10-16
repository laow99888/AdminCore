"""将旧单项目数据安全归属到指定租户。默认只预览，不写入数据库。"""
from uuid import UUID

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import BaseModel, Tenant


class Command(BaseCommand):
    help = '统计或将所有未归属租户的基座记录归属到指定租户（默认只预览）'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', required=True, help='租户 UUID 或 slug')
        parser.add_argument('--apply', action='store_true', help='确认执行写入；不提供时只输出预览')

    def handle(self, *args, **options):
        tenant = self._get_tenant(options['tenant'])
        rows = []
        for model in apps.get_models():
            if not issubclass(model, BaseModel) or model._meta.abstract:
                continue
            manager = getattr(model, 'all_objects', model._base_manager)
            count = manager.filter(tenant__isnull=True).count()
            if count:
                rows.append((model, count))

        total = sum(count for _, count in rows)
        if not options['apply']:
            self._write_result(tenant, rows, total, applied=False)
            self.stdout.write(self.style.WARNING('仅预览，未修改数据；确认后追加 --apply 执行。'))
            return

        with transaction.atomic():
            for model, _ in rows:
                manager = getattr(model, 'all_objects', model._base_manager)
                manager.filter(tenant__isnull=True).update(tenant_id=tenant.pk)
        self._write_result(tenant, rows, total, applied=True)

    @staticmethod
    def _get_tenant(identifier):
        try:
            UUID(str(identifier))
            tenant = Tenant.objects.filter(pk=identifier).first()
        except (ValueError, TypeError, AttributeError):
            tenant = Tenant.objects.filter(slug=identifier).first()
        if tenant is None:
            raise CommandError('找不到租户，请提供有效 UUID 或 slug')
        if tenant.status != Tenant.STATUS_ACTIVE:
            raise CommandError('只能将旧数据归属到处于 active 状态的租户')
        return tenant

    def _write_result(self, tenant, rows, total, *, applied):
        self.stdout.write(f'租户: {tenant.slug} ({tenant.pk})')
        self.stdout.write(f'模式: {"已写入" if applied else "预览"}; 记录数: {total}')
        for model, count in rows:
            self.stdout.write(f'  {model._meta.label}: {count}')
