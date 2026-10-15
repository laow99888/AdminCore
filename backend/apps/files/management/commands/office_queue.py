"""受限宿主协议，字节与令牌只走管道；不接受路径、URL或命令。"""
import base64
import json
import sys
import uuid
from django.core.management.base import BaseCommand, CommandError
from apps.files import office_preview


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate')
        result[key] = value
    return result


class Command(BaseCommand):
    help = '专属 Office 预览宿主执行器协议'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['claim', 'finish', 'fail', 'cleanup'])

    def handle(self, *args, **options):
        try:
            action = options['action']
            if action == 'cleanup':
                office_preview.cleanup()
                result = {'cleaned': True}
            elif action == 'claim':
                result = office_preview.claim()
                if result:
                    result['source'] = base64.b64encode(result['source']).decode('ascii')
            else:
                data = sys.stdin.read(14 * 1024 * 1024 + 1)
                if len(data) > 14 * 1024 * 1024:
                    raise ValueError('oversized')
                payload = json.loads(data, object_pairs_hook=unique)
                expected = {'job_id', 'token', 'pdf'} if action == 'finish' else {'job_id', 'token', 'code'}
                if not isinstance(payload, dict) or set(payload) != expected:
                    raise ValueError('fields')
                identifier = uuid.UUID(payload['job_id'])
                if action == 'finish':
                    output = base64.b64decode(payload['pdf'], validate=True)
                    office_preview.finish(identifier, payload['token'], output=output)
                else:
                    office_preview.finish(identifier, payload['token'], code=payload['code'])
                result = {'updated': True}
            self.stdout.write(json.dumps(result, ensure_ascii=False))
        except Exception:
            # Command output must never expose uploaded bytes, credentials or parser details.
            raise CommandError('Office 预览协议、权限、文件或领取状态无效') from None
