"""仅独立 foundation PostgreSQL 库：公告发布竞争与幂等重放。"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.notifications.models import Announcement, Notification
from apps.logs.models import OperationLog

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connections['default'].vendor == 'postgresql'
suffix = uuid.uuid4().hex[:12]
User = get_user_model()
admins = [User.objects.create_superuser(f'announcement-{suffix}-{n}', password='Fixture#Secure27835') for n in range(2)]


def token_for(user):
    token = RefreshToken.for_user(user)
    token['session_version'] = user.session_version
    return str(token.access_token)


tokens = [token_for(user) for user in admins]


def race(row, same_key=False):
    barrier = Barrier(2)
    def publish(n):
        try:
            client = APIClient(HTTP_HOST='backend')
            client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens[0 if same_key else n]}')
            barrier.wait(timeout=10)
            response = client.post(f'/api/v1/notifications/announcements/manage/{row.pk}/publish/',
                {'version': 1}, format='json', HTTP_IDEMPOTENCY_KEY=f'{suffix}-{row.id}-' + ('same' if same_key else str(n)))
            return response.status_code, response.json()
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(publish, range(2)))


before = Notification.objects.count()
row = Announcement.objects.create(title='并发发布', content='fixture', created_by=admins[0], updated_by=admins[0])
results = race(row)
assert sorted(code for code, _ in results) == [200, 409], results
row.refresh_from_db()
assert row.version == 2 and row.status == 'published'
assert OperationLog.objects.filter(resource='announcement', resource_id=str(row.pk)).count() == 1
row = Announcement.objects.create(title='幂等发布', content='fixture', created_by=admins[0], updated_by=admins[0])
results = race(row, same_key=True)
assert [code for code, _ in results] == [200, 200], results
assert results[0][1] == results[1][1]
assert OperationLog.objects.filter(resource='announcement', resource_id=str(row.pk)).count() == 1
assert Notification.objects.count() == before
print('PostgreSQL 公告不同管理员同版本发布竞争、同键双请求及单审计/无扇出全部通过')
