"""只读预检下一次部署的模块组合，不写配置、不修改运行中服务或数据库。"""
import json
import os

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from apps.core.modules import MODULES, PRESETS, resolve_modules
from apps.core.version import MODULE_CONTRACT_VERSION


class Command(BaseCommand):
    help = '只读校验模块契约、依赖与互斥，显示相对当前进程的启停影响'

    def add_arguments(self, parser):
        parser.add_argument('--preset', choices=tuple(PRESETS))
        parser.add_argument('--modules', help='逗号分隔的完整模块集合；空字符串代表关闭全部可选模块')

    def handle(self, *args, **options):
        preset = options['preset'] or settings.ADMINCORE_PRESET
        explicit = options['modules']
        if options['preset'] is None and explicit is None:
            explicit = ','.join(settings.ADMINCORE_MODULES)
        try:
            selected = resolve_modules(preset, explicit, production=os.getenv('DJANGO_ENV') == 'production')
        except ImproperlyConfigured as exc:
            raise CommandError(str(exc)) from exc
        current = set(settings.ADMINCORE_MODULES)
        self.stdout.write(json.dumps({
            'contract_version': MODULE_CONTRACT_VERSION, 'preset': preset, 'modules': list(selected),
            'enable': sorted(set(selected) - current), 'disable': sorted(current - set(selected)),
            'dependencies': {module.key: list(module.dependencies) for module in MODULES if module.key in selected},
            'requires_restart': current != set(selected) or preset != settings.ADMINCORE_PRESET,
            'retains_tables_and_data': True,
        }, ensure_ascii=False, indent=2))
