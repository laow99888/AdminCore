"""
用户模块测试：CRUD 统一响应包、批量操作、重置密码
"""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestUserCrudEnvelope:
    def test_create_returns_unified_envelope(self, admin_client):
        """回归：ModelViewSet 写操作曾返回裸 serializer 数据，违反统一响应规范"""
        res = admin_client.post(
            '/api/v1/users/',
            {'username': 'alice', 'email': 'alice@example.com', 'password': 'Alice#12345'},
            format='json',
        )
        assert res.status_code == 201
        body = res.json()
        assert body['code'] == 200
        assert body['message'] == '创建成功'
        assert body['data']['username'] == 'alice'

    def test_partial_update_returns_unified_envelope(self, admin_client, member_user):
        res = admin_client.patch(
            f'/api/v1/users/{member_user.id}/',
            {'first_name': '成'},
            format='json',
        )
        assert res.status_code == 200
        body = res.json()
        assert body['code'] == 200
        assert body['data']['first_name'] == '成'

    def test_destroy_returns_unified_envelope(self, admin_client, member_user):
        res = admin_client.delete(f'/api/v1/users/{member_user.id}/')
        assert res.status_code == 200
        assert res.json() == {'code': 200, 'message': '删除成功', 'data': None}
        assert not User.objects.filter(id=member_user.id).exists()

    def test_list_paginated_envelope(self, admin_client, member_user):
        res = admin_client.get('/api/v1/users/')
        assert res.status_code == 200
        body = res.json()
        assert body['code'] == 200
        assert {u['username'] for u in body['data']['items']} >= {'admin', 'member'}
        assert body['data']['pagination']['total'] >= 2

    def test_reset_password_action_still_wrapped(self, admin_client, member_user):
        res = admin_client.post(
            f'/api/v1/users/{member_user.id}/reset_password/',
            {'password': 'NewPass#12345'},
            format='json',
        )
        assert res.status_code == 200
        assert res.json()['code'] == 200
        member_user.refresh_from_db()
        assert member_user.check_password('NewPass#12345')
