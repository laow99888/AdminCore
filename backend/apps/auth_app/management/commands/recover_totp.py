"""仅运维终端恢复失去双因素设备/密钥的账号，不提供 HTTP 绕过入口。"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.auth_app.models import TOTPDevice
from apps.auth_app.totp import clear_pending
from apps.logs.models import OperationLog


class Command(BaseCommand):
    help = '明确确认目标用户名及原因后，关闭其双因素并撤销全部登录会话'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('--confirm-username', required=True)
        parser.add_argument('--reason', required=True)

    def handle(self, *args, **options):
        username = options['username']
        reason = options['reason'].strip()
        self.stdout.write('此操作将关闭指定账号的双因素认证、删除恢复码，并撤销其全部登录会话。')
        if options['confirm_username'] != username or not reason or len(reason) > 200 or not reason.isprintable():
            raise CommandError('必须精确确认用户名，并提供 1-200 字的单行恢复原因')
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().filter(username=username).first()
            if user is None:
                raise CommandError('指定账号不存在')
            device = TOTPDevice.objects.select_for_update().filter(user=user).first()
            if device is None or not (device.active_secret or device.pending_secret):
                raise CommandError('指定账号没有可恢复的双因素设置')
            device.active_secret = ''
            device.recovery_hashes = []
            device.last_counter = -1
            clear_pending(device)
            device.save()
            user.session_version += 1
            user.save(update_fields=['session_version', 'updated_at'])
            OperationLog.objects.create(user=None, action='update', resource='totp', resource_id=str(user.pk),
                                        description=f'offline_totp_recovery; target={user.username}; reason={reason}',
                                        ip_address='127.0.0.1')
        self.stdout.write(self.style.SUCCESS('双因素已关闭，原登录会话已撤销；请重新登录并设置双因素。'))
