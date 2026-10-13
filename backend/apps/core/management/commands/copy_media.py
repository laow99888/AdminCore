"""停写维护窗口内复制媒体；保留对象键和源文件，不修改数据库引用。"""
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.management.base import BaseCommand, CommandError
from django.utils.module_loading import import_string

from apps.core.media_storage import copy_exact, digest, media_keys
from config.storage import storage_settings


class Command(BaseCommand):
    help = '预览或复制本地与 S3 媒体；必须先停止所有写入方，默认只预览'

    def add_arguments(self, parser):
        parser.add_argument('--source', choices=('local', 's3'), required=True)
        parser.add_argument('--destination', choices=('local', 's3'), required=True)
        parser.add_argument('--execute', action='store_true')

    def handle(self, *args, **options):
        if options['source'] == options['destination']:
            raise CommandError('源与目标不能相同')
        environment = {**os.environ, 'ADMINCORE_STORAGE_BACKEND': 's3'}
        config = storage_settings(environment)['default']
        remote = import_string(config['BACKEND'])(**config['OPTIONS'])
        storages = {'local': FileSystemStorage(location=settings.MEDIA_ROOT), 's3': remote}
        source, destination = storages[options['source']], storages[options['destination']]
        keys = list(media_keys(source))
        # 先复核全部冲突，再执行复制，避免途中才发现不同内容的同名对象。
        missing = []
        for key in keys:
            if destination.exists(key):
                if digest(source, key) != digest(destination, key):
                    raise CommandError('存在内容不同的同名媒体，拒绝覆盖；源文件保持不变')
            else:
                missing.append(key)
        self.stdout.write(f'源文件 {len(keys)} 个，待复制 {len(missing)} 个，已一致 {len(keys) - len(missing)} 个')
        if not options['execute']:
            self.stdout.write('仅预览；停写后使用 --execute，复制成功后再修改存储模式并重启服务')
            return
        for key in missing:
            copy_exact(source, key, destination, key)
        self.stdout.write(self.style.SUCCESS('复制及 SHA-256 校验完成，源文件与数据库引用均保留'))
