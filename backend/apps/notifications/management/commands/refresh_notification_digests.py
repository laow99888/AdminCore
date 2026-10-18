"""调度可重复执行的有界到期刷新；无提前刷新和任意租户切换。"""
import json
from django.core.management.base import BaseCommand, CommandError
from apps.notifications.digests import MAX_REFRESH, refresh_due


class Command(BaseCommand):
    help = '刷新已到期的业务通知摘要（最多500条）；默认只处理全局，--all-tenants显式处理所有租户。'

    def create_parser(self, *args, **kwargs):
        parser = super().create_parser(*args, **kwargs)
        parser.allow_abbrev = False
        return parser

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--all-tenants', action='store_true')

    def handle(self, *args, **options):
        if not 1 <= options['limit'] <= MAX_REFRESH:
            raise CommandError('limit必须为1至500')
        self.stdout.write(json.dumps(refresh_due(limit=options['limit'], all_tenants=options['all_tenants'])))
