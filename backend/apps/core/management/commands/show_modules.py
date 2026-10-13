import json
from django.core.management.base import BaseCommand
from apps.core.modules import capabilities


class Command(BaseCommand):
    help = '显示模块契约、依赖和启用状态，不修改数据库'

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(capabilities(), ensure_ascii=False, indent=2))
