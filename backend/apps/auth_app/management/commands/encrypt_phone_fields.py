"""存量手机号检查/单向加密迁移，不打印字段值或记录标识。"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

from apps.core.fields import PREFIX, FieldEncryptionUnavailable, field_cipher, validate_phone
from apps.users.models import UserProfile


class Command(BaseCommand):
    help = '默认仅统计用户/旧资料手机号；--apply 按有界批次加密，不提供解密降级'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--batch-size', type=int, default=200)
        parser.add_argument('--database', default='default')
        parser.add_argument('--model', choices=['all', 'user', 'profile'], default='all')

    def handle(self, *args, **options):
        batch_size, alias = options['batch_size'], options['database']
        if not 1 <= batch_size <= 1000:
            raise CommandError('批次大小必须为 1-1000')
        if options['apply']:
            try:
                field_cipher()
            except FieldEncryptionUnavailable:
                raise CommandError('转换要求有效的手机号加密密钥') from None
        connection = connections[alias]
        models = [get_user_model(), UserProfile]
        if options['model'] != 'all':
            models = [models[0 if options['model'] == 'user' else 1]]
        totals = dict(scanned=0, blank=0, plaintext=0, encrypted=0, invalid=0, unavailable=0, converted=0)
        for model in models:
            last_id = None
            phone_field = model._meta.get_field('phone')
            table = connection.ops.quote_name(model._meta.db_table)
            pk = connection.ops.quote_name(model._meta.pk.column)
            phone = connection.ops.quote_name(phone_field.column)
            while True:
                with transaction.atomic(using=alias):
                    where = f' WHERE {pk} > %s' if last_id is not None else ''
                    params = [last_id, batch_size] if last_id is not None else [batch_size]
                    lock = ' FOR UPDATE' if options['apply'] and connection.features.has_select_for_update else ''
                    with connection.cursor() as cursor:
                        cursor.execute(f'SELECT {pk}, {phone} FROM {table}{where} ORDER BY {pk} LIMIT %s{lock}', params)
                        rows = cursor.fetchall()
                    if not rows:
                        break
                    last_id = rows[-1][0]
                    pending = []
                    batch_invalid = False
                    for identifier, stored in rows:
                        totals['scanned'] += 1
                        try:
                            if stored == '':
                                totals['blank'] += 1
                            elif isinstance(stored, str) and stored.startswith(PREFIX):
                                totals['encrypted'] += 1
                                phone_field.from_db_value(stored, None, connection)
                            else:
                                validate_phone(stored)
                                totals['plaintext'] += 1
                                pending.append((identifier, stored))
                        except ValidationError:
                            totals['invalid'] += 1
                            batch_invalid = True
                        except FieldEncryptionUnavailable:
                            totals['unavailable'] += 1
                            batch_invalid = True
                    if options['apply']:
                        if batch_invalid:
                            raise CommandError('本批存在无效或不可解密手机号，已回滚本批；修复配置/存量后可幂等重跑')
                        for identifier, value in pending:
                            model.objects.using(alias).filter(pk=identifier).update(phone=value)
                        totals['converted'] += len(pending)
        self.stdout.write('模式=' + ('apply' if options['apply'] else 'check') + '; '
                          + '; '.join(f'{key}={value}' for key, value in totals.items()))
