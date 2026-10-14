"""仅隔离 foundation PostgreSQL：令牌轮换、设备撤销和等待期间的鉴权。"""
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Barrier, Event
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections, transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.auth_app.models import AuthSession
from apps.auth_app.profile import update_profile
from apps.auth_app.sessions import issue_session

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connections['default'].vendor == 'postgresql'
User = get_user_model()
password = 'Fixture#Secure27835'
user = User.objects.create_user('session-race-' + uuid.uuid4().hex[:10], password=password)
refresh = issue_session(user)
other = issue_session(user)


def client_for(token=None):
    client = APIClient(HTTP_HOST='backend')
    if token:
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token))
    return client


barrier = Barrier(2)


def rotate(_):
    try:
        barrier.wait(timeout=10)
        response = client_for().post('/api/v1/auth/refresh/', {'refresh': str(refresh)}, format='json')
        return response.status_code, response.json()
    finally:
        connections.close_all()


with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(rotate, range(2)))
assert sorted(code for code, _ in results) == [200, 400], results
rotated = next(body['data'] for code, body in results if code == 200)
assert client_for(rotated['access']).get('/api/v1/auth/me/').status_code == 200
assert client_for(other.access_token).get('/api/v1/auth/me/').status_code == 200
response = client_for(other.access_token).delete('/api/v1/auth/sessions/' + refresh['sid'] + '/',
                                                {'current_password': password}, format='json')
assert response.status_code == 200, response.json()
assert client_for(rotated['access']).get('/api/v1/auth/me/').status_code == 401
assert client_for().post('/api/v1/auth/refresh/', {'refresh': rotated['refresh']}, format='json').status_code == 400
assert client_for(other.access_token).get('/api/v1/auth/me/').status_code == 200

# 已通过初始鉴权但在用户行锁上等待的敏感写，必须重查设备撤销。
locked, release = Event(), Event()
request = SimpleNamespace(user=user, auth=other.access_token, META={'REMOTE_ADDR': '127.0.0.1'})


def revoke_and_hold():
    try:
        with transaction.atomic():
            User.objects.select_for_update().get(pk=user.pk)
            session = AuthSession.objects.select_for_update().get(pk=other['sid'])
            session.revoked_at = timezone.now()
            session.save(update_fields=['revoked_at'])
            locked.set()
            assert release.wait(10)
    finally:
        connections.close_all()


def waiting_write():
    try:
        try:
            update_profile(request, {'profile_version': 1, 'bio': '不可写入'})
        except AuthenticationFailed as error:
            assert error.status_code == 401
            return
        raise AssertionError('已撤销设备仍能在等待后写入资料')
    finally:
        connections.close_all()


with ThreadPoolExecutor(max_workers=2) as pool:
    first = pool.submit(revoke_and_hold)
    assert locked.wait(10)
    second = pool.submit(waiting_write)
    try:
        try:
            second.result(timeout=0.25)
            raise AssertionError('资料写入未等待用户行锁')
        except TimeoutError:
            pass
    finally:
        release.set()
    first.result(timeout=10)
    second.result(timeout=10)
user.refresh_from_db()
assert user.profile_version == 1

# 两个管理员同时撤销对方，固定用户锁顺序避免交叉死锁；败方不能以旧会话继续撤销。
admins = [User.objects.create_superuser('session-admin-' + uuid.uuid4().hex[:10], password=password)
          for _ in range(2)]
admin_tokens = [issue_session(actor) for actor in admins]
barrier = Barrier(2)


def revoke_other(index):
    try:
        barrier.wait(timeout=10)
        response = client_for(admin_tokens[index].access_token).post(
            f'/api/v1/auth/online-users/{admins[1-index].pk}/revoke/',
            {'current_password': password}, format='json')
        return response.status_code
    finally:
        connections.close_all()


with ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(revoke_other, index) for index in range(2)]
    statuses = [future.result(timeout=15) for future in futures]
assert sorted(statuses) == [200, 401], statuses
assert sum(client_for(token.access_token).get('/api/v1/auth/me/').status_code == 200
           for token in admin_tokens) == 1
print('PostgreSQL refresh 单次轮换、指定设备撤销隔离、等待写复核、管理员互撤无死锁全部通过')
