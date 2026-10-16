"""受限宿主机备份协议；stdout 仅输出 JSON，不输出凭据或错误详情。"""
import json
import sys
import uuid

from django.core.management.base import BaseCommand, CommandError
from apps.tasks.backup import FAILURE_CODES, claim, claim_restore, complete, finish_restore, runner_heartbeat


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_field')
        result[key] = value
    return result


class Command(BaseCommand):
    help = '宿主备份执行器领取/完成/失败登记'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['claim', 'finish', 'fail', 'heartbeat', 'claim-restore', 'finish-restore'])
        parser.add_argument('record_id', nargs='?')
        parser.add_argument('--token', type=uuid.UUID)
        parser.add_argument('--code', choices=sorted(FAILURE_CODES))

    def handle(self, *args, **options):
        try:
            if options['action'] == 'claim':
                if options['record_id'] or options['token'] or options['code']:
                    raise ValueError('invalid_arguments')
                result = claim()
            elif options['action'] in {'heartbeat', 'claim-restore'}:
                if options['record_id'] or options['token'] or options['code']:
                    raise ValueError('invalid_arguments')
                if options['action'] == 'heartbeat':
                    payload = sys.stdin.read(262145)
                    if len(payload) > 262144:
                        raise ValueError('invalid_status')
                    result = runner_heartbeat(json.loads(payload, object_pairs_hook=unique_object))
                else:
                    result = claim_restore()
            elif options['action'] == 'finish-restore':
                if not options['record_id'] or options['token'] or options['code']:
                    raise ValueError('invalid_arguments')
                payload = sys.stdin.read(2049)
                if len(payload) > 2048:
                    raise ValueError('invalid_restore_result')
                data = json.loads(payload, object_pairs_hook=unique_object)
                if set(data) != {'status', 'error'}:
                    raise ValueError('invalid_restore_result')
                result = finish_restore(uuid.UUID(options['record_id']), data['status'], data['error'])
            else:
                if not options['record_id'] or not options['token']:
                    raise ValueError('invalid_arguments')
                record_id = uuid.UUID(options['record_id'])
                if options['action'] == 'finish':
                    if options['code']:
                        raise ValueError('invalid_arguments')
                    payload = sys.stdin.read(16385)
                    if len(payload) > 16384:
                        raise ValueError('invalid_result')
                    complete(record_id, options['token'], result=json.loads(payload, object_pairs_hook=unique_object))
                else:
                    if not options['code']:
                        raise ValueError('invalid_arguments')
                    complete(record_id, options['token'], code=options['code'])
                result = {'record_id': str(record_id), 'updated': True}
            self.stdout.write(json.dumps(result, ensure_ascii=False))
        except (ValueError, TypeError, KeyError):
            raise CommandError('备份队列参数、结果或领取状态无效') from None
