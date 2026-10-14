"""全员公告的可见性、权限、版本、幂等及审计隔离测试。"""
import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from apps.notifications.models import Announcement, Notification
from apps.notifications.announcement_services import authorize
from apps.logs.models import OperationLog

pytestmark = pytest.mark.django_db
PUBLIC = '/api/v1/notifications/announcements/'
MANAGE = PUBLIC + 'manage/'


def create(client, **extra):
    return client.post(MANAGE, {'title': '系统升级', 'content': '内部纯文本公告', 'version': 0, **extra}, format='json')


def transition(client, row, action, version=None, key=None):
    return client.post(f'{MANAGE}{row.id}/{action}/', {'version': row.version if version is None else version}, format='json', **({'HTTP_IDEMPOTENCY_KEY': key} if key else {}))


@pytest.fixture
def draft(admin_client):
    result = create(admin_client)
    assert result.status_code == 201
    return Announcement.objects.get(pk=result.json()['data']['id'])


def test_anonymous_cannot_read_or_write():
    client = APIClient()
    assert client.get(PUBLIC).status_code == 401
    assert create(client).status_code == 401


def test_member_can_only_read_published(admin_client, member_client, draft):
    assert member_client.get(PUBLIC).json()['data']['pagination']['total'] == 0
    assert member_client.get(f'{PUBLIC}{draft.pk}/').status_code == 404
    assert transition(admin_client, draft, 'publish').status_code == 200
    data = member_client.get(PUBLIC).json()['data']
    assert data['pagination']['total'] == 1
    assert data['items'][0]['status'] == 'published'
    assert member_client.get(f'{PUBLIC}{draft.pk}/').status_code == 200


def test_admin_public_view_does_not_leak_drafts(admin_client, draft):
    assert admin_client.get(PUBLIC).json()['data']['items'] == []
    assert admin_client.get(MANAGE).json()['data']['pagination']['total'] == 1


def test_announcement_reads_writes_and_denials_cannot_be_cached(admin_client, member_client, draft):
    responses = [APIClient().get(PUBLIC), member_client.get(PUBLIC),
                 member_client.get(MANAGE), admin_client.get(MANAGE),
                 transition(admin_client, draft, 'publish'),
                 transition(admin_client, draft, 'publish')]
    assert [response.status_code for response in responses] == [401, 200, 403, 200, 200, 409]
    assert all(response['Cache-Control'] == 'private, no-store' for response in responses)


@pytest.mark.parametrize('method,path', [('get', MANAGE), ('post', MANAGE), ('patch', MANAGE + '00000000-0000-0000-0000-000000000000/'), ('post', MANAGE + '00000000-0000-0000-0000-000000000000/publish/')])
def test_member_cannot_manage(member_client, method, path):
    assert getattr(member_client, method)(path, {'title': 'a', 'content': 'b', 'version': 0}, format='json').status_code == 403


@pytest.mark.parametrize('extra', [{'title': ''}, {'content': '  '}, {'title': 'x' * 201}, {'content': 'x' * 20001}, {'status': 'published'}, {'version': -1}, {'created_by': 'x'}])
def test_create_validation(admin_client, extra):
    assert create(admin_client, **extra).status_code == 400
    assert not Announcement.objects.exists()


def test_new_version_must_be_zero(admin_client):
    assert create(admin_client, version=1).status_code == 409


def test_edit_version_and_publish_state(admin_client, draft):
    url = f'{MANAGE}{draft.pk}/'
    assert admin_client.patch(url, {'title': '更新', 'content': '更新内容', 'version': 1}, format='json').status_code == 200
    assert admin_client.patch(url, {'title': '覆盖', 'content': '覆盖内容', 'version': 1}, format='json').status_code == 409
    draft.refresh_from_db()
    assert draft.version == 2 and draft.title == '更新'
    assert transition(admin_client, draft, 'publish').status_code == 200
    assert admin_client.patch(url, {'title': '覆盖', 'content': '覆盖内容', 'version': 3}, format='json').status_code == 409


def test_publish_withdraw_republish(admin_client, member_client, draft):
    assert transition(admin_client, draft, 'withdraw').status_code == 409
    assert transition(admin_client, draft, 'publish').status_code == 200
    draft.refresh_from_db(); published = draft.published_at
    assert transition(admin_client, draft, 'publish').status_code == 409
    assert transition(admin_client, draft, 'withdraw').status_code == 200
    assert member_client.get(f'{PUBLIC}{draft.pk}/').status_code == 404
    draft.refresh_from_db()
    assert draft.status == 'withdrawn'
    assert transition(admin_client, draft, 'publish').status_code == 200
    draft.refresh_from_db()
    assert draft.version == 4 and draft.published_at >= published


def test_publish_replay_single_audit_no_fanout(admin_client, draft):
    before = Notification.objects.count()
    first = transition(admin_client, draft, 'publish', key='publish-once')
    again = transition(admin_client, draft, 'publish', key='publish-once')
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json() and again['Idempotency-Replayed'] == 'true'
    assert OperationLog.objects.filter(resource='announcement', resource_id=str(draft.id)).count() == 2
    assert Notification.objects.count() == before
    assert transition(admin_client, draft, 'publish', version=2, key='publish-once').status_code == 409


def test_create_replay_and_changed_body_conflict(admin_client):
    first = admin_client.post(MANAGE, {'title': 'a', 'content': 'b', 'version': 0}, format='json', HTTP_IDEMPOTENCY_KEY='create-once')
    again = admin_client.post(MANAGE, {'title': 'a', 'content': 'b', 'version': 0}, format='json', HTTP_IDEMPOTENCY_KEY='create-once')
    assert first.json() == again.json() and Announcement.objects.count() == 1
    assert admin_client.post(MANAGE, {'title': 'c', 'content': 'b', 'version': 0}, format='json', HTTP_IDEMPOTENCY_KEY='create-once').status_code == 409


def test_transition_rejects_extra_fields(admin_client, draft):
    assert admin_client.post(f'{MANAGE}{draft.pk}/publish/', {'version': 1, 'status': 'published'}, format='json').status_code == 400


def test_revoked_staff_cannot_replay(admin_client, admin_user, draft):
    assert transition(admin_client, draft, 'publish', key='replay-revoked').status_code == 200
    get_user_model().objects.filter(pk=admin_user.pk).update(is_staff=False, is_superuser=False)
    assert transition(admin_client, draft, 'publish', key='replay-revoked').status_code == 403


@pytest.mark.parametrize('field,value,error', [('is_active', False, AuthenticationFailed), ('session_version', 1, AuthenticationFailed), ('must_change_password', True, PermissionDenied), ('is_staff', False, PermissionDenied)])
def test_transaction_authorization_reloads_actor(admin_user, field, value, error):
    if field == 'is_staff':
        get_user_model().objects.filter(pk=admin_user.pk).update(is_superuser=False)
    stale = get_user_model().objects.get(pk=admin_user.pk)
    get_user_model().objects.filter(pk=admin_user.pk).update(**{field: value})
    request = SimpleNamespace(user=stale, auth={'session_version': 0})
    with transaction.atomic(), pytest.raises(error):
        authorize(request, 'announcement:update', lock=True)


def test_write_rechecks_permission_before_replay(admin_client, draft):
    with patch('apps.notifications.announcement_services.has_permission_code', return_value=False):
        assert transition(admin_client, draft, 'publish').status_code == 403


def test_disabled_module_blocks_public_and_manage(admin_client, member_client, draft):
    with override_settings(ADMINCORE_MODULES=()):
        assert member_client.get(PUBLIC).status_code == 404
        assert admin_client.get(MANAGE).status_code == 404
        assert transition(admin_client, draft, 'publish').status_code == 404


def test_new_users_read_no_personal_data(admin_client, draft):
    assert transition(admin_client, draft, 'publish').status_code == 200
    user = get_user_model().objects.create_user('later-reader', password='Fixture#Readable123')
    client = APIClient(); client.force_authenticate(user)
    data = client.get(f'{PUBLIC}{draft.pk}/').json()['data']
    assert not {'created_by', 'updated_by', 'email', 'phone', 'username'} & data.keys()
    log = OperationLog.objects.filter(resource='announcement', resource_id=str(draft.pk)).last()
    assert draft.content not in log.description
    assert len(json.loads(log.description)['content_sha256']) == 64


def test_search_status_pagination(admin_client):
    for title in ['匹配一', '匹配二', '其他']:
        assert create(admin_client, title=title).status_code == 201
    data = admin_client.get(MANAGE, {'search': '匹配', 'status': 'draft', 'page_size': 1}).json()['data']
    assert data['pagination']['total'] == 2 and len(data['items']) == 1


def test_no_delete_or_put_api(admin_client, draft):
    assert admin_client.delete(f'{MANAGE}{draft.pk}/').status_code == 405
    assert admin_client.put(f'{MANAGE}{draft.pk}/', {}, format='json').status_code == 405
    assert admin_client.post(PUBLIC, {}, format='json').status_code == 405


def test_invalid_identifier_is_not_server_error(admin_client):
    assert admin_client.post(f'{MANAGE}bad-id/publish/', {'version': 1}, format='json').status_code == 404


@pytest.mark.parametrize('data', [[{'version': 1}], 'wrong type', None])
def test_non_object_payload_rejected(admin_client, draft, data):
    assert admin_client.post(f'{MANAGE}{draft.pk}/publish/', data, format='json').status_code == 400
    assert admin_client.post(MANAGE, data, format='json').status_code == 400


def test_audit_failure_rolls_back(admin_client):
    with patch('apps.notifications.announcement_services.audit', side_effect=RuntimeError('fixture audit failure')):
        assert create(admin_client).status_code == 500
    assert not Announcement.objects.exists()
