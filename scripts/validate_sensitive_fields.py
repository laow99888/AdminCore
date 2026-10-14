"""隔离 foundation PostgreSQL 的联系方式权限、加密转换与行锁验收。

在隔离 backend 内用 manage.py shell 执行；不读取正式凭据、不输出手机号或密钥。
"""
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import io
import secrets
from threading import Event
import time
from unittest.mock import patch
import uuid

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connections, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auth_app.models import AuthSession
from apps.auth_app.sessions import issue_session
from apps.core.fields import EncryptedPhoneField, PREFIX
from apps.core.modules import module_enabled
from apps.logs.models import OperationLog
from apps.users.models import UserProfile

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connections['default'].vendor == 'postgresql', '必须使用 PostgreSQL'
User = get_user_model()
CREATED, CHECKS, TOKENS = [], [], []
PHONE, REPLACEMENT = '13876543210', '13976543210'
started_window = int(time.time() // 60)


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)
    print('通过：敏感字段验收 ' + label, flush=True)


def fixture(admin=False):
    password = secrets.token_urlsafe(40)
    user = User.objects.create_user('sensitive-' + uuid.uuid4().hex[:12], password=password,
        email='fixture-' + uuid.uuid4().hex[:12] + '@example.test', phone='',
        is_staff=admin, is_superuser=admin)
    CREATED.append(user.pk)
    return user, password


def bearer(user):
    token = issue_session(user)
    TOKENS.append(str(token['sid']))
    client = APIClient(HTTP_HOST='backend', REMOTE_ADDR='127.0.5.1')
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
    return client, token


def stored(model, identifier):
    connection = connections['default']
    table = connection.ops.quote_name(model._meta.db_table)
    pk = connection.ops.quote_name(model._meta.pk.column)
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT phone FROM {table} WHERE {pk} = %s', [identifier])
        return cursor.fetchone()[0]


def seed_legacy(model, identifier):
    # 运维测试夹具：模拟历史明文，不通过产品 API 绕过字段校验。
    connection = connections['default']
    table = connection.ops.quote_name(model._meta.db_table)
    pk = connection.ops.quote_name(model._meta.pk.column)
    with connection.cursor() as cursor:
        cursor.execute(f'UPDATE {table} SET phone=%s WHERE {pk}=%s', [PHONE, identifier])


def other_contacts():
    result = []
    connection = connections['default']
    for model in (User, UserProfile):
        table = connection.ops.quote_name(model._meta.db_table)
        pk = connection.ops.quote_name(model._meta.pk.column)
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT {pk}, phone FROM {table} ORDER BY {pk}')
            rows = cursor.fetchall()
        excluded = CREATED if model is User else list(UserProfile.objects.filter(user_id__in=CREATED).values_list('pk', flat=True))
        result.extend((table, str(identifier), value) for identifier, value in rows if identifier not in excluded)
    return result


def job(function):
    connections.close_all()
    try:
        return function()
    finally:
        connections.close_all()


def reveal(client, target, password):
    return client.post(f'/api/v1/users/{target.pk}/sensitive/',
        {'current_password': password}, format='json')


def conversion_race(target):
    """转换拿到旧值时持锁，新写入必须等待，并最终保留新值。"""
    entered, release, writing = Event(), Event(), Event()
    original = EncryptedPhoneField.get_prep_value
    report = io.StringIO()
    updater_pid = []

    def prepare(field, value):
        if value == PHONE:
            entered.set()
            assert release.wait(12), '转换锁屏障超时'
        return original(field, value)

    def update():
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT pg_backend_pid()')
            updater_pid.append(cursor.fetchone()[0])
        writing.set()
        User.objects.filter(pk=target.pk).update(phone=REPLACEMENT)

    with ThreadPoolExecutor(max_workers=2) as pool:
        with patch.object(EncryptedPhoneField, 'get_prep_value', prepare):
            conversion = pool.submit(job, lambda: call_command('encrypt_phone_fields', apply=True,
                model='user', batch_size=1, stdout=report))
            try:
                assert entered.wait(12), '转换未到达持锁阶段'
                writer = pool.submit(job, update)
                assert writing.wait(5), '并发写入未启动'
                blocked = False
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with connections['default'].cursor() as cursor:
                        cursor.execute('SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s', updater_pid)
                        row = cursor.fetchone()
                    if row and row[0] == 'Lock':
                        blocked = True
                        break
                    time.sleep(.025)
                check('转换与并发编辑由真实PostgreSQL行锁串行化', blocked and not writer.done())
            finally:
                release.set()
            conversion.result(timeout=15)
            writer.result(timeout=15)
    check('转换不会用旧快照覆盖并发新手机号', User.objects.get(pk=target.pk).phone == REPLACEMENT
          and stored(User, target.pk).startswith(PREFIX))


def revoked_waiter(actor, password, target):
    """HTTP已认证后等用户锁，撤销sid必须在锁内再次拒绝。"""
    client, token = bearer(actor)
    requesting = Event()
    request_pid = []
    before = OperationLog.objects.filter(user=actor, action='read_sensitive').count()

    def request():
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT pg_backend_pid()')
            request_pid.append(cursor.fetchone()[0])
        requesting.set()
        return reveal(client, target, password)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            User.objects.select_for_update().get(pk=actor.pk)
            future = pool.submit(job, request)
            assert requesting.wait(5), '敏感请求未启动'
            waiting = False
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with connections['default'].cursor() as cursor:
                    cursor.execute('SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s', request_pid)
                    row = cursor.fetchone()
                if row and row[0] == 'Lock':
                    waiting = True
                    break
                time.sleep(.025)
            check('敏感查看等待服务器用户锁', waiting and not future.done())
            AuthSession.objects.filter(pk=token['sid']).update(revoked_at=timezone.now())
        response = future.result(timeout=15)
    check('等待期间已撤销的会话锁内失败且无明文审计', response.status_code == 401
        and PHONE not in str(response.data)
        and OperationLog.objects.filter(user=actor, action='read_sensitive').count() == before)


key = getattr(settings, 'ADMINCORE_FIELD_ENCRYPTION_KEY', '') or Fernet.generate_key().decode('ascii')
try:
    with override_settings(ADMINCORE_FIELD_ENCRYPTION_ENABLED=False, ADMINCORE_FIELD_ENCRYPTION_KEY=''):
        actor, password = fixture(admin=True)
        target, _ = fixture()
        profile = UserProfile.objects.create(user=target, phone='')
        seed_legacy(User, target.pk)
        seed_legacy(UserProfile, profile.pk)
        check('默认关闭时存量明文兼容', stored(User, target.pk) == PHONE
              and stored(UserProfile, profile.pk) == PHONE)
    with override_settings(ADMINCORE_FIELD_ENCRYPTION_ENABLED=True, ADMINCORE_FIELD_ENCRYPTION_KEY=key):
        baseline = other_contacts()
        assert all(not value for _, _, value in baseline), '拒绝转换含其他验收账号非空手机号的库'
        output = io.StringIO()
        call_command('encrypt_phone_fields', stdout=output)
        check('检查模式只报告统计且不变更存储', 'converted=0' in output.getvalue()
              and PHONE not in output.getvalue() and stored(User, target.pk) == PHONE)
        conversion_race(target)
        User.objects.filter(pk=actor.pk).update(phone=PHONE)
        output = io.StringIO()
        call_command('encrypt_phone_fields', apply=True, batch_size=1, stdout=output)
        check('用户与旧资料转换后数据库无手机号明文', PHONE not in stored(User, actor.pk)
              and stored(UserProfile, profile.pk).startswith(PREFIX))
        call_command('encrypt_phone_fields', apply=True, batch_size=1, stdout=io.StringIO())
        check('重复转换幂等且ORM返回完整合法原值', UserProfile.objects.get(pk=profile.pk).phone == PHONE
              and User.objects.get(pk=target.pk).phone == REPLACEMENT)
        client, _ = bearer(actor)
        response = client.get(f'/api/v1/users/{target.pk}/')
        check('加密联系人管理响应始终脱敏', response.status_code == 200
              and target.email not in str(response.data) and PHONE not in str(response.data)
              and REPLACEMENT not in str(response.data) and PREFIX not in str(response.data))
        response = reveal(client, target, password)
        check('密码确认后只返回邮箱手机号且禁止缓存', response.status_code == 200
              and response.data['data'] == {'email': target.email, 'phone': REPLACEMENT}
              and response['Cache-Control'] == 'private, no-store')
        response = client.get('/api/v1/data-io/export/?resource=users&export_format=csv')
        if module_enabled('data_io'):
            rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
            check('真实数据库CSV导出始终脱敏', response.status_code == 200
                  and target.email not in str(rows) and PHONE not in str(rows) and REPLACEMENT not in str(rows))
        else:
            check('精简部署关闭导出且不泄露联系方式', response.status_code == 404
                  and target.email not in str(response.json()) and REPLACEMENT not in str(response.json()))
        response = client.get('/api/v1/auth/me/')
        check('本人资料通过ORM解密保留原值', response.status_code == 200 and response.data['data']['phone'] == PHONE)
        revoked_waiter(actor, password, target)
        audit = str(list(OperationLog.objects.filter(user_id__in=CREATED).values()))
        check('明文联系人密码密钥不进入审计', all(value not in audit for value in (PHONE, REPLACEMENT, password, key, target.email)))
        with override_settings(ADMINCORE_FIELD_ENCRYPTION_KEY=Fernet.generate_key().decode('ascii')):
            response = client.get(f'/api/v1/users/{target.pk}/')
            check('错误密钥失败关闭不返回明文或密文', response.status_code == 503
                  and all(value not in str(response.data) for value in (PHONE, REPLACEMENT, PREFIX, key)))
        with override_settings(ADMINCORE_FIELD_ENCRYPTION_ENABLED=False, ADMINCORE_FIELD_ENCRYPTION_KEY=''):
            response = client.get('/api/v1/auth/me/')
            check('关闭开关和移除密钥不能降级读取已加密值', response.status_code == 503
                  and PREFIX not in str(response.data) and PHONE not in str(response.data))
        check('本专项没有修改其他验收账号的存储值', other_contacts() == baseline)
finally:
    # 只删除登记的随机夹具；QuerySet.delete先加载User会解密，故保留本脚本密钥。
    with override_settings(ADMINCORE_FIELD_ENCRYPTION_KEY=key):
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        OutstandingToken.objects.filter(user_id__in=CREATED).delete()
        User.objects.filter(pk__in=CREATED).delete()
    keys = []
    for window in range(started_window, int(time.time() // 60) + 1):
        for identifier in CREATED:
            for identity in (f'user:{identifier}', f'scope:{identifier}:user:sensitive-read'):
                keys.append('password-confirmation:' + hashlib.sha256(identity.encode()).hexdigest() + f':{window}')
            keys.append(f'throttle_user_{identifier}')
    cache.delete_many(keys)
    assert not User.objects.filter(pk__in=CREATED).exists(), '敏感字段夹具清理不完整'
    connections.close_all()
print('敏感字段 PostgreSQL 验收通过：' + str(len(CHECKS)) + ' 项；随机夹具已清理，无常驻进程')
