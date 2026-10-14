"""精简无 worker 部署的受信任终端入口；默认只预览。"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.tasks.lifecycle import clean
from apps.tasks.maintenance import maintenance_lock


class Command(BaseCommand):
    help = '预览历史日志/登记导入源清理；实际清理需 --execute --confirm 执行清理'

    def add_arguments(self, parser):
        parser.add_argument('--execute', action='store_true')
        parser.add_argument('--confirm', default='')

    def handle(self, *args, **options):
        if options['execute'] and options['confirm'] != '执行清理':
            raise CommandError('实际清理必须传入 --confirm 执行清理')
        with maintenance_lock('lifecycle') as acquired:
            if not acquired:
                raise CommandError('同类维护任务正在执行')
            result = clean(dry_run=not options['execute'])
        self.stdout.write(json.dumps(result, ensure_ascii=False))
