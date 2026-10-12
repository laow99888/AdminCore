"""
认证系统测试
"""

import pytest
from django.contrib.auth import get_user_model

from .conftest import ADMIN_PASSWORD

User = get_user_model()


class TestLogin:
    def test_login_success_returns_tokens_and_user(self, client, admin_user):
        res = client.post('/api/v1/auth/login/',
                          {'username': 'admin', 'password': ADMIN_PASSWORD}, format='json')
        assert res.status_code == 200
        data = res.json()
        assert data['access'] and data['refresh']
        assert data['user']['username'] == 'admin'

    def test_login_wrong_password_401(self, client, admin_user):
        res = client.post('/api/v1/auth/login/',
                          {'username': 'admin', 'password': 'wrong-password'}, format='json')
        assert res.status_code == 401

    def test_refresh_works_without_bearer_token(self, client, admin_user):
        """回归：refresh 曾误加 IsAuthenticated——access 过期时恰恰无法携带有效 Bearer，
        刷新端点必须允许匿名调用（鉴权只看 body 中的 refresh token）"""
        login = client.post('/api/v1/auth/login/',
                            {'username': 'admin', 'password': ADMIN_PASSWORD}, format='json').json()
        res = client.post('/api/v1/auth/refresh/', {'refresh': login['refresh']}, format='json')
        assert res.status_code == 200
        assert res.json()['data']['access']

    def test_refresh_with_garbage_token_400(self, client):
        res = client.post('/api/v1/auth/refresh/', {'refresh': 'not-a-jwt'}, format='json')
        assert res.status_code == 400

    def test_login_failure_recorded_in_login_log(self, client, admin_user):
        from apps.logs.models import LoginLog
        client.post('/api/v1/auth/login/', {'username': 'admin', 'password': 'bad'}, format='json')
        assert LoginLog.objects.filter(username='admin', status='failed').exists()

    def test_login_success_increments_login_count(self, client, admin_user):
        before = admin_user.login_count
        client.post('/api/v1/auth/login/', {'username': 'admin', 'password': ADMIN_PASSWORD}, format='json')
        admin_user.refresh_from_db()
        assert admin_user.login_count == before + 1


class TestMe:
    def test_me_requires_auth(self, client):
        assert client.get('/api/v1/auth/me/').status_code == 401

    def test_me_returns_current_user(self, member_client, member_user):
        res = member_client.get('/api/v1/auth/me/')
        assert res.status_code == 200
        assert res.json()['data']['username'] == 'member'


class TestChangePassword:
    def test_change_password_and_login_with_new(self, client, member_client, member_user):
        res = member_client.post('/api/v1/auth/change_password/', {
            'old_password': 'Member#12345',
            'new_password': 'NewPass#67890',
            'new_password2': 'NewPass#67890',
        }, format='json')
        assert res.status_code == 200

        res = client.post('/api/v1/auth/login/',
                          {'username': 'member', 'password': 'NewPass#67890'}, format='json')
        assert res.status_code == 200

    def test_change_password_wrong_old_password(self, member_client):
        res = member_client.post('/api/v1/auth/change_password/', {
            'old_password': 'wrong',
            'new_password': 'NewPass#67890',
            'new_password2': 'NewPass#67890',
        }, format='json')
        assert res.status_code == 400
