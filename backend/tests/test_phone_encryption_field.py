"""手机号加密字段存储契约，不以序列化响应代替原始数据库验证。"""
from io import StringIO
import os
import subprocess
import sys

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.models import Case, F, Value, When
from django.test import override_settings

from apps.core.fields import PREFIX, NAMESPACE, FieldEncryptionUnavailable
from apps.users.models import UserProfile

User = get_user_model()
PHONE = '+86 13800138000'


def raw_phone(model, pk):
    key = model._meta.pk.get_db_prep_value(pk, connection)
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT phone FROM {connection.ops.quote_name(model._meta.db_table)} WHERE id=%s', [key])
        return cursor.fetchone()[0]


def write_raw(model, pk, value):
    key = model._meta.pk.get_db_prep_value(pk, connection)
    with connection.cursor() as cursor:
        cursor.execute(f'UPDATE {connection.ops.quote_name(model._meta.db_table)} SET phone=%s WHERE id=%s', [value, key])


@pytest.fixture
def encryption():
    key = Fernet.generate_key().decode()
    with override_settings(ADMINCORE_FIELD_ENCRYPTION_ENABLED=True, ADMINCORE_FIELD_ENCRYPTION_KEY=key):
        yield key


@pytest.mark.django_db
@pytest.mark.parametrize('legacy', [False, True])
def test_both_phone_models_encrypt_storage_preserve_api_length(member_user, encryption, legacy):
    obj = UserProfile.objects.create(user=member_user, phone=PHONE) if legacy else member_user
    obj.phone = PHONE
    obj.save(update_fields=['phone'])
    stored = raw_phone(type(obj), obj.pk)
    assert stored.startswith(PREFIX) and PHONE not in stored
    assert Fernet(encryption.encode()).decrypt(stored[len(PREFIX):].encode()) == NAMESPACE + PHONE.encode()
    obj.refresh_from_db()
    assert obj.phone == PHONE and isinstance(obj.phone, str)
    assert obj._meta.get_field('phone').max_length == 20
    assert obj._meta.get_field('phone').db_type(connection) == 'text'


@pytest.mark.django_db
def test_default_plaintext_and_key_presence_prevents_disabled_downgrade(member_user, encryption):
    with override_settings(ADMINCORE_FIELD_ENCRYPTION_ENABLED=False, ADMINCORE_FIELD_ENCRYPTION_KEY=''):
        member_user.phone = PHONE
        member_user.save(update_fields=['phone'])
        assert raw_phone(User, member_user.pk) == PHONE
    with override_settings(ADMINCORE_FIELD_ENCRYPTION_ENABLED=False):
        User.objects.filter(pk=member_user.pk).update(phone=PHONE)
        assert raw_phone(User, member_user.pk).startswith(PREFIX)
        member_user.refresh_from_db()
        member_user.save(update_fields=['phone'])
        assert raw_phone(User, member_user.pk).startswith(PREFIX)
    with override_settings(ADMINCORE_FIELD_ENCRYPTION_ENABLED=False, ADMINCORE_FIELD_ENCRYPTION_KEY=''):
        with pytest.raises(FieldEncryptionUnavailable):
            member_user.save(update_fields=['phone'])
        with pytest.raises(FieldEncryptionUnavailable):
            member_user.refresh_from_db()
        for value in (PHONE, Value(PHONE)):
            with pytest.raises(FieldEncryptionUnavailable), transaction.atomic():
                User.objects.filter(pk=member_user.pk).update(phone=value)
        fresh = User(pk=member_user.pk, phone=PHONE)
        with pytest.raises(FieldEncryptionUnavailable), transaction.atomic():
            User.objects.bulk_update([fresh], ['phone'])
        assert raw_phone(User, member_user.pk).startswith(PREFIX)


@pytest.mark.django_db
def test_bulk_and_queryset_value_writes_encrypt(member_user, encryption):
    users = [User(username=f'phone-bulk-{i}', phone=PHONE) for i in range(2)]
    User.objects.bulk_create(users)
    for user in users:
        assert raw_phone(User, user.pk).startswith(PREFIX)
        user.phone = '13900139000'
    User.objects.bulk_update(users, ['phone'])
    assert all(User.objects.get(pk=user.pk).phone == '13900139000' for user in users)
    for value in (PHONE, Value(PHONE)):
        User.objects.filter(pk=member_user.pk).update(phone=value)
        assert raw_phone(User, member_user.pk).startswith(PREFIX)
        assert User.objects.get(pk=member_user.pk).phone == PHONE
    with pytest.raises(ValidationError, match='不支持数据库表达式'):
        User.objects.filter(pk=member_user.pk).update(phone=F('phone'))


@pytest.mark.django_db
def test_bulk_conflict_writes_and_case_null_default(member_user, encryption):
    User.objects.bulk_create([User(username=member_user.username, phone=PHONE)], ignore_conflicts=True)
    User.objects.bulk_create([User(username=member_user.username, phone=PHONE)], update_conflicts=True,
                             update_fields=['phone'], unique_fields=['username'])
    assert raw_phone(User, member_user.pk).startswith(PREFIX)
    assert User.objects.get(pk=member_user.pk).phone == PHONE
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(pk=member_user.pk).update(phone=Case(When(username='not-matching', then=Value(PHONE))))
    assert User.objects.get(pk=member_user.pk).phone == PHONE


@pytest.mark.django_db
@pytest.mark.parametrize('value', ['1' * 21, '+' + '1' * 20, 'not-a-phone', PREFIX + 'forged', 123, None])
def test_invalid_or_forged_inputs_fail_without_database_write(member_user, encryption, value):
    with pytest.raises(ValidationError) as error:
        with transaction.atomic():
            User.objects.filter(pk=member_user.pk).update(phone=value)
    assert str(value) not in str(error.value)
    assert raw_phone(User, member_user.pk) == ''


@pytest.mark.django_db
def test_corrupt_wrong_key_wrong_namespace_fail_closed(member_user, encryption):
    wrong_namespace = PREFIX + Fernet(encryption.encode()).encrypt(b'other-field:secret').decode()
    for stored in (PREFIX + 'broken', wrong_namespace):
        write_raw(User, member_user.pk, stored)
        with pytest.raises(FieldEncryptionUnavailable) as error:
            User.objects.get(pk=member_user.pk)
        assert stored not in str(error.value) and 'secret' not in str(error.value)
    write_raw(User, member_user.pk, '')
    User.objects.filter(pk=member_user.pk).update(phone=PHONE)
    with override_settings(ADMINCORE_FIELD_ENCRYPTION_KEY=Fernet.generate_key().decode()):
        with pytest.raises(FieldEncryptionUnavailable):
            User.objects.get(pk=member_user.pk)


@pytest.mark.django_db
def test_allow_clear_but_require_key_for_nonempty_write(member_user):
    with override_settings(ADMINCORE_FIELD_ENCRYPTION_ENABLED=True, ADMINCORE_FIELD_ENCRYPTION_KEY=''):
        with pytest.raises(FieldEncryptionUnavailable):
            with transaction.atomic():
                User.objects.filter(pk=member_user.pk).update(phone=PHONE)
        User.objects.filter(pk=member_user.pk).update(phone='')
        assert raw_phone(User, member_user.pk) == ''


@pytest.mark.django_db
def test_conversion_default_stats_only_apply_bounded_and_idempotent(member_user, encryption):
    legacy = UserProfile.objects.create(user=member_user)
    write_raw(User, member_user.pk, PHONE)
    write_raw(UserProfile, legacy.pk, PHONE)
    output = StringIO()
    call_command('encrypt_phone_fields', batch_size=1, stdout=output)
    assert 'plaintext=2' in output.getvalue() and 'converted=0' in output.getvalue()
    assert PHONE not in output.getvalue() and str(member_user.pk) not in output.getvalue()
    assert raw_phone(User, member_user.pk) == PHONE
    output = StringIO()
    call_command('encrypt_phone_fields', apply=True, batch_size=1, stdout=output)
    assert 'converted=2' in output.getvalue()
    assert raw_phone(User, member_user.pk).startswith(PREFIX)
    assert raw_phone(UserProfile, legacy.pk).startswith(PREFIX)
    output = StringIO()
    call_command('encrypt_phone_fields', apply=True, batch_size=1, stdout=output)
    assert 'encrypted=2' in output.getvalue() and 'converted=0' in output.getvalue()


@pytest.mark.django_db
def test_conversion_invalid_legacy_fails_without_values_and_rolls_back_batch(member_user, encryption):
    valid = User.objects.create(username='valid-legacy-phone')
    write_raw(User, valid.pk, PHONE)
    write_raw(User, member_user.pk, 'secret-bad-phone')
    output = StringIO()
    call_command('encrypt_phone_fields', stdout=output)
    assert 'invalid=1' in output.getvalue() and 'secret-bad-phone' not in output.getvalue()
    with pytest.raises(CommandError) as error:
        call_command('encrypt_phone_fields', apply=True, stdout=StringIO())
    assert 'secret-bad-phone' not in str(error.value)
    assert raw_phone(User, member_user.pk) == 'secret-bad-phone'
    assert raw_phone(User, valid.pk) == PHONE
    for size in (0, 1001):
        with pytest.raises(CommandError):
            call_command('encrypt_phone_fields', batch_size=size, stdout=StringIO())


@pytest.mark.parametrize('enabled,key', [('True', ''), ('False', 'invalid-private-key')])
def test_settings_reject_unusable_encryption_configuration(enabled, key):
    env = {**os.environ, 'ADMINCORE_FIELD_ENCRYPTION_ENABLED': enabled,
           'ADMINCORE_FIELD_ENCRYPTION_KEY': key, 'DJANGO_SETTINGS_MODULE': 'config.settings.testing'}
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', 'import config.settings.base'], env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode != 0 and 'ImproperlyConfigured' in result.stderr
    assert 'invalid-private-key' not in result.stderr
