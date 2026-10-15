"""批量响应中的逐项状态描述整批结果，不探测不可访问对象是否存在。"""
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model

from apps.example.models import WorkItem
from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole

pytestmark = pytest.mark.django_db
URL = '/api/v1/users/bulk_action/'
User = get_user_model()


def assert_results(response, identifiers, status):
    assert response.status_code == status
    assert response.json()['data'] == {
        'atomic': True,
        'succeeded': len(identifiers) if status == 200 else 0,
        'failed': 0 if status == 200 else len(identifiers),
        'results': [{'id': str(identifier), 'status': status} for identifier in identifiers],
    }


@pytest.mark.parametrize('action', ['activate', 'deactivate', 'delete'])
def test_success_reports_each_submitted_id_in_input_order(admin_client, member_user, action):
    other = User.objects.create_user('bulk-other', is_active=False)
    identifiers = sorted([other.pk, member_user.pk], reverse=True)
    response = admin_client.post(URL, {'action': action, 'user_ids': identifiers}, format='json',
                                 HTTP_X_REQUEST_ID='bulk-results-success')
    assert_results(response, identifiers, 200)
    if action == 'delete':
        assert not User.objects.filter(pk__in=identifiers).exists()
    else:
        assert list(User.objects.filter(pk__in=identifiers).values_list('is_active', flat=True)) == [action == 'activate'] * 2
    assert OperationLog.objects.get(request_id='bulk-results-success', resource_id='').batch_results == response.json()['data']['results']


@pytest.mark.parametrize('duplicate', [False, True])
def test_rejected_batch_reports_no_changes_and_no_existence_details(admin_client, member_user, duplicate):
    identifiers = [member_user.pk, member_user.pk if duplicate else uuid4()]
    response = admin_client.post(URL, {'action': 'deactivate', 'user_ids': identifiers}, format='json')
    assert_results(response, identifiers, 403)
    member_user.refresh_from_db()
    assert member_user.is_active


def test_protected_delete_reports_all_items_unapplied(admin_client, member_user):
    other = User.objects.create_user('bulk-protected-other')
    item = WorkItem.objects.create(title='受保护的引用', creator=member_user)
    identifiers = [other.pk, member_user.pk]
    response = admin_client.post(URL, {'action': 'delete', 'user_ids': identifiers}, format='json')
    assert_results(response, identifiers, 409)
    assert User.objects.filter(pk__in=identifiers).count() == 2
    assert WorkItem.objects.filter(pk=item.pk).exists()
    assert not OperationLog.objects.filter(resource='user', action='delete').exists()
    assert str(item.pk) not in response.content.decode()


def test_audit_failure_reports_no_committed_items(admin_client, member_user):
    with patch('apps.logs.audit.write_audit', side_effect=RuntimeError('private fixture detail')):
        response = admin_client.post(URL, {'action': 'deactivate', 'user_ids': [member_user.pk]}, format='json')
    assert_results(response, [member_user.pk], 500)
    member_user.refresh_from_db()
    assert member_user.is_active
    assert 'private fixture detail' not in response.content.decode()


def test_update_permission_cannot_authorize_bulk_delete(member_client, member_user):
    role = Role.objects.create(name='仅允许更新')
    permission = Permission.objects.create(name='更新用户', code='user:update', resource='user', action='update')
    RolePermission.objects.create(role=role, permission=permission)
    UserRole.objects.create(user=member_user, role=role)
    identifiers = [member_user.pk, uuid4()]
    response = member_client.post(URL, {'action': 'delete', 'user_ids': identifiers}, format='json')
    assert_results(response, identifiers, 403)
    assert User.objects.filter(pk=member_user.pk).exists()


@pytest.mark.parametrize('identifiers', [[], ['invalid'], [str(uuid4())] * 1001])
def test_invalid_or_oversized_batch_keeps_validation_error(admin_client, identifiers):
    response = admin_client.post(URL, {'action': 'deactivate', 'user_ids': identifiers}, format='json')
    assert response.status_code == 400
    assert 'user_ids' in response.json()['data']
