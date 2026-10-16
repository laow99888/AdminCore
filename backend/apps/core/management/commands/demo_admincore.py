"""独立演示项目初始化/重置；正式项目没有此命令的可用执行路径。"""
import hmac
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test.utils import override_settings
from apps.core.demo import validate_target, demo_lock, require_empty_database, seed_data
from apps.core.models import BootstrapState


class Command(BaseCommand):
    help = '初始化独立演示数据；重置必须提供本实例确认令牌，永不猜测数据库'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true')
        parser.add_argument('--confirm', default='', help='仅从演示项目私有环境读取，不应写入日志')

    def handle(self, *args, **options):
        instance, token, marker, accounts = validate_target()
        reset = options['reset']
        if reset and not hmac.compare_digest(options['confirm'], token):
            raise CommandError('演示重置确认令牌不匹配；未修改任何数据')
        required = {'files', 'tasks', 'notifications', 'data_io', 'approvals', 'system', 'organization', 'example'}
        if not required <= set(settings.ADMINCORE_MODULES):
            raise CommandError('完整演示数据要求启用所有代表模块')
        with demo_lock(instance):
            owned = BootstrapState.objects.filter(key=marker).exists()
            if reset and not owned:
                raise CommandError('数据库缺少本实例签名演示标记，拒绝重置')
            if owned and not reset:
                self.stdout.write('本实例演示数据已初始化；保留用户后续修改。')
                return
            if not reset:
                require_empty_database()
            with transaction.atomic():
                if reset:
                    call_command('flush', interactive=False, verbosity=0)
                    # flush 不重新运行数据迁移，恢复默认关闭的基础单例。
                    from apps.ip_policy.models import IPPolicy
                    IPPolicy.objects.create(pk=1)
                # 普通bootstrap只创建环境中独立随机管理员，禁止走旧固定demo路径。
                with override_settings(ADMINCORE_PRESET='standard'):
                    call_command('bootstrap_admincore', stdout=self.stdout)
                seed_data(accounts)
                BootstrapState.objects.create(key=marker)
        self.stdout.write(self.style.SUCCESS('独立演示数据已就绪；随机凭据仅保存在演示项目私有环境文件。'))
