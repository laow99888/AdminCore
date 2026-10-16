import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


def definition(*users, mode='all', kind='parallel'):
    return {
        'nodes': [
            {'id': 'start', 'type': 'start'},
            {'id': 'review', 'type': kind, 'name': '审核', 'mode': mode,
             'assignee_ids': [str(user.id) for user in users]},
            {'id': 'end', 'type': 'end'},
        ],
        'edges': [{'from': 'start', 'to': 'review'}, {'from': 'review', 'to': 'end'}],
    }


def create_flow(admin_client, admin_user, *users, mode='all', kind='parallel'):
    response = admin_client.post('/api/v1/approvals/flows/', {
        'name': '采购审批', 'code': 'purchase-flow',
        'definition': definition(*users, mode=mode, kind=kind),
    }, format='json')
    assert response.status_code == 201, response.content
    flow_id = response.json()['data']['id']
    response = admin_client.post(f'/api/v1/approvals/flows/{flow_id}/publish/', format='json')
    assert response.status_code == 200, response.content
    return flow_id


@pytest.mark.django_db
def test_flow_design_publish_and_parallel_completion(admin_client, admin_user, member_user):
    second = User.objects.create_user('reviewer2', 'reviewer2@example.com', 'Member#12345')
    flow_id = create_flow(admin_client, admin_user, admin_user, second)
    response = admin_client.post('/api/v1/approvals/', {
        'title': '流程申请', 'request_type': 'other', 'content': '内容', 'flow_id': flow_id,
    }, format='json')
    assert response.status_code == 201, response.content
    request_id = response.json()['data']['id']
    assert response.json()['data']['flow'] == flow_id
    assert len(response.json()['data']['steps']) == 2

    first = admin_client.post(f'/api/v1/approvals/{request_id}/approve/', {'comment': '同意'}, format='json')
    assert first.status_code == 200
    assert first.json()['data']['status'] == 'pending'
    second_client = admin_client.__class__()
    second_client.force_authenticate(second)
    final = second_client.post(f'/api/v1/approvals/{request_id}/approve/', {'comment': '同意'}, format='json')
    assert final.status_code == 200
    assert final.json()['data']['status'] == 'approved'
    done = second_client.get('/api/v1/approvals/?box=done')
    assert done.status_code == 200
    assert any(row['id'] == request_id for row in done.json()['data']['items'])


@pytest.mark.django_db
def test_or_sign_skips_other_and_advanced_actions(admin_client, admin_user, member_user):
    second = User.objects.create_user('reviewer3', 'reviewer3@example.com', 'Member#12345')
    flow_id = create_flow(admin_client, admin_user, admin_user, second, mode='any', kind='or')
    response = admin_client.post('/api/v1/approvals/', {
        'title': '或签申请', 'request_type': 'other', 'content': '内容', 'flow_id': flow_id,
    }, format='json')
    request_id = response.json()['data']['id']
    target = User.objects.create_user('target', 'target@example.com', 'Member#12345')
    transfer_payload = {'target_user_id': str(target.id)}
    transfer = admin_client.post(f'/api/v1/approvals/{request_id}/transfer/', transfer_payload,
                                 format='json', HTTP_IDEMPOTENCY_KEY='advanced-transfer-1')
    assert transfer.status_code == 200
    replay = admin_client.post(f'/api/v1/approvals/{request_id}/transfer/', transfer_payload,
                               format='json', HTTP_IDEMPOTENCY_KEY='advanced-transfer-1')
    assert replay.status_code == 200
    assert replay.get('Idempotency-Replayed') == 'true'
    delegate = APIClientForUser(target).post(f'/api/v1/approvals/{request_id}/delegate/', {'target_user_id': str(member_user.id)}, format='json')
    assert delegate.status_code == 200
    cc = admin_client.post(f'/api/v1/approvals/{request_id}/cc/', {'user_ids': [str(member_user.id)]}, format='json')
    assert cc.status_code == 200
    assert cc.json()['data']['cc_recipients'][0]['user'] == str(member_user.id)
    assert admin_client.post(f'/api/v1/approvals/{request_id}/approve/', format='json').status_code == 403


class APIClientForUser:
    def __init__(self, user):
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.client.force_authenticate(user)

    def post(self, *args, **kwargs):
        return self.client.post(*args, **kwargs)


@pytest.mark.django_db
def test_flow_rejects_cycle_and_published_update(admin_client, admin_user, member_user):
    bad = definition(admin_user)
    bad['edges'].append({'from': 'review', 'to': 'start'})
    response = admin_client.post('/api/v1/approvals/flows/', {
        'name': '坏流程', 'code': 'bad-flow', 'definition': bad,
    }, format='json')
    assert response.status_code == 400
    flow_id = create_flow(admin_client, admin_user, admin_user)
    response = admin_client.put(f'/api/v1/approvals/flows/{flow_id}/', {
        'name': '修改', 'code': 'purchase-flow', 'definition': definition(admin_user),
    }, format='json')
    assert response.status_code == 400
