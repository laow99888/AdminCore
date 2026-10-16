from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.ip_policy.models import IPPolicy
from apps.logs.audit import snapshot, write_audit


class Command(BaseCommand):
    help = '在部署终端禁用 IP 策略并写入审计；不提供 HTTP 恢复后门'

    def add_arguments(self, parser):
        parser.add_argument('--confirm-disable', action='store_true')
        parser.add_argument('--reason', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        if not options['confirm_disable'] or not options['reason'].strip() or len(options['reason']) > 200:
            raise CommandError('恢复必须明确确认并提供不超过200字的原因')
        row = IPPolicy.objects.select_for_update().filter(pk=1).first()
        if row is None:
            raise CommandError('策略不存在，请先执行数据库迁移')
        if row.enabled:
            before = snapshot('ip_policy', row)
            row.enabled = False
            row.version += 1
            row.save()
            write_audit(resource='ip_policy', identifier=1, action='emergency_disable', before=before,
                        after=snapshot('ip_policy', row), description=options['reason'].strip())
        self.stdout.write(self.style.SUCCESS('IP 策略已禁用；恢复操作已完成'))
