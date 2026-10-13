"""
审批流程测试
"""


def submit(client, admin_user, title='测试申请', **extra):
    payload = {
        'title': title,
        'request_type': 'other',
        'content': '测试内容',
        'assignee_id': str(admin_user.id),
    }
    payload.update(extra)
    return client.post('/api/v1/approvals/', payload, format='json')


class TestSubmit:
    def test_create_and_notify_assignee(self, member_client, admin_user, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            res = submit(member_client, admin_user)
        assert res.status_code == 201
        assert res.json()['data']['status'] == 'pending'
        # 审批人收到通知
        assert admin_user.notifications.filter(notification_type='approval', is_read=False).exists()

    def test_sent_box_only_shows_own(self, member_client, admin_user, member_user):
        submit(member_client, admin_user)
        res = member_client.get('/api/v1/approvals/?box=sent')
        items = res.json()['data']['items']
        assert len(items) == 1
        assert items[0]['applicant_name'] == 'member'


class TestDecide:
    def test_non_assignee_cannot_approve(self, member_client, admin_client, admin_user):
        req_id = submit(member_client, admin_user).json()['data']['id']
        res = member_client.post(f'/api/v1/approvals/{req_id}/approve/', {'comment': ''}, format='json')
        assert res.status_code == 403

    def test_approve_updates_status_and_notifies_applicant(self, member_client, admin_client,
                                                           admin_user, member_user, django_capture_on_commit_callbacks):
        req_id = submit(member_client, admin_user, title='采购显示器').json()['data']['id']
        with django_capture_on_commit_callbacks(execute=True):
            res = admin_client.post(f'/api/v1/approvals/{req_id}/approve/', {'comment': '同意'}, format='json')
        assert res.status_code == 200
        assert res.json()['data']['status'] == 'approved'
        # 申请人收到通过通知
        assert member_user.notifications.filter(title__contains='已通过').exists()

    def test_reject_flow(self, member_client, admin_client, admin_user):
        req_id = submit(member_client, admin_user).json()['data']['id']
        res = admin_client.post(f'/api/v1/approvals/{req_id}/reject/', {'comment': '不符合要求'}, format='json')
        assert res.json()['data']['status'] == 'rejected'

    def test_done_box_shows_processed(self, member_client, admin_client, admin_user):
        req_id = submit(member_client, admin_user).json()['data']['id']
        admin_client.post(f'/api/v1/approvals/{req_id}/approve/', format='json')
        res = admin_client.get('/api/v1/approvals/?box=done')
        assert len(res.json()['data']['items']) == 1

    def test_double_approve_rejected(self, member_client, admin_client, admin_user):
        req_id = submit(member_client, admin_user).json()['data']['id']
        assert admin_client.post(f'/api/v1/approvals/{req_id}/approve/', format='json').status_code == 200
        res = admin_client.post(f'/api/v1/approvals/{req_id}/approve/', format='json')
        assert res.status_code == 400


class TestCancel:
    def test_applicant_cancel_pending(self, member_client, admin_client, admin_user):
        req_id = submit(member_client, admin_user).json()['data']['id']
        res = member_client.post(f'/api/v1/approvals/{req_id}/cancel/', format='json')
        assert res.json()['data']['status'] == 'cancelled'
        # 已撤回不能再处理
        assert admin_client.post(f'/api/v1/approvals/{req_id}/approve/', format='json').status_code == 400

    def test_assignee_cannot_cancel(self, member_client, admin_client, admin_user):
        req_id = submit(member_client, admin_user).json()['data']['id']
        res = admin_client.post(f'/api/v1/approvals/{req_id}/cancel/', format='json')
        assert res.status_code == 403
