"""
通知系统测试
"""


class TestNotificationCenter:
    def test_unread_count(self, admin_client, member_client, member_user, admin_user):
        admin_client.post('/api/v1/notifications/', {
            'recipient_ids': [str(member_user.id)], 'title': '第一条', 'content': '',
        }, format='json')
        admin_client.post('/api/v1/notifications/', {
            'recipient_ids': [str(member_user.id)], 'title': '第二条', 'content': '',
        }, format='json')
        res = member_client.get('/api/v1/notifications/unread_count/')
        assert res.json()['data']['count'] == 2

    def test_mark_all_read(self, admin_client, member_client, member_user, admin_user):
        admin_client.post('/api/v1/notifications/', {
            'recipient_ids': [str(member_user.id)], 'title': '通知',
        }, format='json')
        member_client.post('/api/v1/notifications/mark_all_read/')
        res = member_client.get('/api/v1/notifications/unread_count/')
        assert res.json()['data']['count'] == 0

    def test_retrieve_is_read_only_and_explicit_action_marks_read(self, admin_client, member_client, member_user, admin_user):
        notification = admin_client.post('/api/v1/notifications/', {
            'recipient_ids': [str(member_user.id)], 'title': '自动已读',
        }, format='json').json()
        # 列表拿到通知 id（发送接口不返回列表）
        item_id = member_client.get('/api/v1/notifications/').json()['data']['items'][0]['id']
        res = member_client.get(f'/api/v1/notifications/{item_id}/')
        assert res.json()['data']['is_read'] is False
        assert member_client.post(f'/api/v1/notifications/{item_id}/mark_read/').status_code == 200
        assert member_client.get(f'/api/v1/notifications/{item_id}/').json()['data']['is_read'] is True

    def test_member_cannot_send(self, member_client, admin_user):
        res = member_client.post('/api/v1/notifications/', {
            'recipient_ids': [str(admin_user.id)], 'title': '越权',
        }, format='json')
        assert res.status_code == 403

    def test_member_only_sees_own_notifications(self, admin_client, member_client, admin_user, member_user):
        admin_client.post('/api/v1/notifications/', {
            'recipient_ids': [str(admin_user.id)], 'title': '给管理员',
        }, format='json')
        admin_client.post('/api/v1/notifications/', {
            'recipient_ids': [str(member_user.id)], 'title': '给成员',
        }, format='json')

        # member 默认视角只能看到自己的
        member_items = member_client.get('/api/v1/notifications/').json()['data']['items']
        assert [i['title'] for i in member_items] == ['给成员']

        # admin 管理视角（scope=all）可以看到全部
        all_items = admin_client.get('/api/v1/notifications/?scope=all').json()['data']['items']
        assert len(all_items) == 2
