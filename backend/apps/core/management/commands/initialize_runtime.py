"""有界等待数据库，并协调多个容器的数据库初始化。"""
import time
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connection, OperationalError


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--bootstrap', action='store_true')
        parser.add_argument('--timeout', type=int, default=180)

    def handle(self, *args, **options):
        timeout = options['timeout']
        if timeout < 1 or timeout > 1800:
            raise CommandError('初始化超时必须在 1 至 1800 秒之间')
        deadline = time.monotonic() + timeout
        if connection.vendor == 'postgresql':
            connection.settings_dict.setdefault('OPTIONS', {}).setdefault('connect_timeout', 5)
        while True:
            try:
                connection.ensure_connection()
                break
            except OperationalError:
                if time.monotonic() >= deadline:
                    raise CommandError('等待数据库超时，请检查连接配置及数据库日志') from None
                self.stdout.write('数据库尚未就绪，稍后重试')
                time.sleep(2)
        acquired = False
        try:
            if connection.vendor == 'postgresql':
                while not acquired:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_try_advisory_lock(%s)', [619863473029])
                        acquired = cursor.fetchone()[0]
                    if not acquired:
                        if time.monotonic() >= deadline:
                            raise CommandError('等待数据库初始化锁超时')
                        time.sleep(2)
            call_command('migrate', interactive=False)
            if options['bootstrap']:
                call_command('bootstrap_admincore')
        finally:
            if acquired:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_unlock(%s)', [619863473029])
