"""
pytest 共享 fixtures
"""

import pytest
import shutil
import tempfile
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture(autouse=True)
def isolated_rate_counters():
    """每个用例隔离限流计数；同一用例内仍检查真实限流行为。"""
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(scope='session', autouse=True)
def cleanup_test_media(request):
    """只清理本次测试创建的媒体目录；失败时保留证据。"""
    root = Path(settings.MEDIA_ROOT).resolve()
    yield
    if request.session.testsfailed:
        print(f'保留失败测试媒体：{root}')
    elif (getattr(settings, 'TESTING', False)
          and root.parent == Path(tempfile.gettempdir()).resolve()
          and root.name.startswith('admincore-test-media-')):
        shutil.rmtree(root)
        print(f'已清理本次测试媒体：{root}')

ADMIN_PASSWORD = 'Admin#12345'
MEMBER_PASSWORD = 'Member#12345'


def _login(username: str, password: str) -> APIClient:
    client = APIClient()
    res = client.post('/api/v1/auth/login/', {'username': username, 'password': password}, format='json')
    token = res.json().get('access')
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser('admin', 'admin@example.com', ADMIN_PASSWORD)


@pytest.fixture
def member_user(db):
    return User.objects.create_user('member', 'member@example.com', MEMBER_PASSWORD)


@pytest.fixture
def admin_client(db, admin_user):
    return _login('admin', ADMIN_PASSWORD)


@pytest.fixture
def member_client(db, member_user):
    return _login('member', MEMBER_PASSWORD)
