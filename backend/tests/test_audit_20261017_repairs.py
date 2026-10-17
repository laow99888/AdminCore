"""多模型审计的可复现安全与一致性回归；全部使用隔离测试库。"""
import hashlib
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.approvals.models import ApprovalFlow, ApprovalRequest, ApprovalStep, ApprovalCC, validate_flow_definition
from apps.core.models import OutboxEvent
from apps.online_forms.validators import validate_definition, validate_record

pytestmark = pytest.mark.django_db
User = get_user_model()


def client(user):
    value = APIClient(); value.force_authenticate(user)
    return value


def graph(*users):
    keys = ['start', *[f'review{i}' for i in range(len(users))], 'end']
    return {'nodes': [{'id': 'start', 'type': 'start'}, *[
        {'id': f'review{i}', 'type': 'user', 'assignee_ids': [str(user.pk)]} for i, user in enumerate(users)
    ], {'id': 'end', 'type': 'end'}], 'edges': [{'from': a, 'to': b} for a, b in zip(keys, keys[1:])]}


def application(admin_user, applicant, *reviewers, code='regression'):
    flow = ApprovalFlow.objects.create(code=code, name=code, created_by=admin_user,
                                      status='published', definition=graph(*reviewers))
    response = client(applicant).post('/api/v1/approvals/', {'title': '私有申请', 'content': '正文', 'flow_id': str(flow.pk)}, format='json')
    assert response.status_code == 201, response.content
    return ApprovalRequest.objects.get(pk=response.data['data']['id'])


def test_cc_requires_object_access_and_recipient_gets_read_only_visibility(admin_user, member_user):
    reviewer = User.objects.create_user('cc-reviewer')
    outsider = User.objects.create_user('cc-outsider')
    recipient = User.objects.create_user('cc-recipient')
    row = application(admin_user, member_user, reviewer)
    url = f'/api/v1/approvals/{row.pk}/'
    assert client(outsider).post(url + 'cc/', {'user_ids': [str(recipient.pk)]}, format='json').status_code == 404
    assert not ApprovalCC.objects.filter(request=row).exists()
    assert client(reviewer).post(url + 'cc/', {'user_ids': [str(recipient.pk)]}, format='json').status_code == 200
    assert client(recipient).get(url).status_code == 200
    assert client(recipient).get('/api/v1/approvals/?box=cc').data['data']['pagination']['total'] == 1
    assert client(recipient).post(url + 'cc/', {'user_ids': [str(outsider.pk)]}, format='json').status_code == 403


def test_transfer_revokes_delegate_and_duplicate_signers_are_conflicts(admin_user, member_user):
    delegate, target = User.objects.create_user('old-delegate'), User.objects.create_user('transfer-target')
    row = application(admin_user, member_user, admin_user)
    url = f'/api/v1/approvals/{row.pk}/'
    admin = client(admin_user)
    assert admin.post(url + 'add-sign/', {'target_user_id': str(admin_user.pk)}, format='json').status_code == 409
    assert admin.post(url + 'delegate/', {'target_user_id': str(delegate.pk)}, format='json').status_code == 200
    assert admin.post(url + 'transfer/', {'target_user_id': str(target.pk)}, format='json').status_code == 200
    assert row.steps.get().delegated_to_id is None
    assert client(delegate).post(url + 'approve/', format='json').status_code in {403, 404}
    assert client(target).post(url + 'approve/', format='json').status_code == 200


def test_disabled_next_reviewer_is_conflict_without_partial_progress(admin_user, member_user):
    next_user = User.objects.create_user('inactive-next')
    row = application(admin_user, member_user, admin_user, next_user)
    next_user.is_active = False; next_user.save(update_fields=['is_active'])
    response = client(admin_user).post(f'/api/v1/approvals/{row.pk}/approve/', format='json')
    assert response.status_code == 409, response.content
    assert row.steps.get().status == 'pending'
    row.refresh_from_db(); assert row.current_node == 'review0'


@pytest.mark.parametrize('action', ['cancel', 'reject'])
def test_terminal_application_closes_steps_and_rejects_participant_changes(admin_user, member_user, action):
    row = application(admin_user, member_user, admin_user)
    actor = member_user if action == 'cancel' else admin_user
    assert client(actor).post(f'/api/v1/approvals/{row.pk}/{action}/', format='json').status_code == 200
    assert not row.steps.filter(status='pending').exists()
    response = client(member_user).post(f'/api/v1/approvals/{row.pk}/cc/', {'user_ids': [str(admin_user.pk)]}, format='json')
    assert response.status_code == 409


def test_branch_graph_cannot_be_silently_published(admin_user, member_user):
    value = graph(admin_user, member_user)
    value['edges'].append({'from': 'start', 'to': 'review1'})
    with pytest.raises(DjangoValidationError):
        validate_flow_definition(value)


def test_referenced_applicant_and_parallel_reviewer_cannot_be_deleted(admin_user, member_user):
    row = application(admin_user, member_user, admin_user)
    for user in (member_user, admin_user):
        with pytest.raises(ProtectedError), transaction.atomic():
            user.delete()
    assert ApprovalRequest.objects.filter(pk=row.pk).exists()


def test_workflow_notifications_include_next_reviewer_and_final_applicant(admin_user, member_user):
    next_user = User.objects.create_user('notify-next')
    row = application(admin_user, member_user, admin_user, next_user)
    url = f'/api/v1/approvals/{row.pk}/approve/'
    assert client(admin_user).post(url, format='json').status_code == 200
    assert OutboxEvent.objects.filter(payload__recipient_ids=[str(next_user.pk)]).exists()
    assert client(next_user).post(url, format='json').status_code == 200
    assert OutboxEvent.objects.filter(payload__recipient_ids=[str(member_user.pk)]).exists()


def test_approval_query_count_does_not_grow_per_row(admin_user, member_user):
    for index in range(5):
        application(admin_user, member_user, admin_user, code=f'queries{index}')
    actor = client(member_user)
    with CaptureQueriesContext(connection) as small:
        assert actor.get('/api/v1/approvals/?page_size=1').status_code == 200
    with CaptureQueriesContext(connection) as large:
        assert actor.get('/api/v1/approvals/?page_size=5').status_code == 200
    assert len(large) <= len(small) + 1


@pytest.mark.parametrize('value', ['', '   ', None])
def test_required_text_cannot_be_empty(value):
    definition = validate_definition({'fields': [{'key': 'title', 'label': '标题', 'type': 'text', 'required': True}]})
    with pytest.raises(ValidationError):
        validate_record(definition, {'title': value})


@pytest.mark.parametrize('field', [
    {'type': 'number', 'default': {'unexpected': 'object'}},
    {'type': 'number', 'default': float('inf')},
    {'type': 'date', 'default': '2026-02-31'},
    {'type': 'text', 'required': 'false'},
])
def test_form_definition_cannot_bypass_runtime_validation(field):
    with pytest.raises(ValidationError):
        validate_definition({'fields': [{'key': 'value', 'label': '值', **field}]})


@pytest.mark.parametrize('resource', ['form', 'report', 'flow'])
def test_design_update_uses_expected_version(settings, admin_user, resource):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'online_forms', 'reports')
    settings.ROOT_URLCONF = 'tests.tenant_object_urls'
    from apps.online_forms.models import OnlineForm
    from apps.reports.models import ReportDefinition
    model, base, definition = {
        'form': (OnlineForm, '/api/v1/online-forms/forms/', {'fields': [{'key': 'title', 'label': '标题', 'type': 'text'}]}),
        'report': (ReportDefinition, '/api/v1/reports/definitions/', {'data_source': 'tasks', 'chart_type': 'table', 'metric': {'field': 'id', 'aggregation': 'count'}}),
        'flow': (ApprovalFlow, '/api/v1/approvals/flows/', graph(admin_user)),
    }[resource]
    row = model.objects.create(code='version-test', name='初始', created_by=admin_user, definition=definition)
    actor = client(admin_user)
    payload = {'name': '新版本', 'version': 1, 'code': row.code, 'definition': definition}
    update = actor.put if resource == 'flow' else actor.patch
    assert update(base + str(row.pk) + '/', payload, format='json').status_code == 200
    payload['name'] = '过期覆盖'
    assert update(base + str(row.pk) + '/', payload, format='json').status_code == 409
    row.refresh_from_db(); assert row.name == '新版本' and row.version == 2


@pytest.mark.parametrize('value', ['not-a-bool', {}, [], 1, None])
def test_report_boolean_filter_rejects_wrong_type(value):
    from apps.reports.validators import validate_definition
    with pytest.raises(ValidationError):
        validate_definition({'data_source': 'users', 'chart_type': 'table', 'metric': {'field': 'id', 'aggregation': 'count'},
                             'filters': [{'field': 'is_active', 'operator': 'eq', 'value': value}]})


def test_resumable_upload_enforces_whitelist_and_cleans_failed_database_commit(admin_client, settings, tmp_path, monkeypatch):
    from apps.files.models import FileModel, ResumableUpload
    settings.MEDIA_ROOT = str(tmp_path)
    assert admin_client.post('/api/v1/files/uploads/', {'name': 'bad.exe', 'total_size': 1, 'chunk_size': 262144}, format='json').status_code == 400
    data = b'A' * 262144
    started = admin_client.post('/api/v1/files/uploads/', {'name': 'valid.txt', 'total_size': len(data), 'chunk_size': len(data)}, format='json')
    identifier = started.data['data']['id']
    assert admin_client.put(f'/api/v1/files/uploads/{identifier}/chunks/0/', data,
        content_type='application/octet-stream', HTTP_X_CHUNK_SHA256=hashlib.sha256(data).hexdigest()).status_code == 200
    original = ResumableUpload.save
    def fail(self, *args, **kwargs):
        if self.status == 'completed': raise IntegrityError('synthetic failure')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(ResumableUpload, 'save', fail)
    assert admin_client.post(f'/api/v1/files/uploads/{identifier}/complete/', format='json').status_code == 500
    assert not FileModel.objects.exists()
    assert not [file for file in tmp_path.rglob('*') if file.is_file() and '.chunks' not in file.parts]


def test_upload_completion_reuses_winner_when_chunks_disappear(admin_client, settings, tmp_path, monkeypatch):
    from django.core.files.storage import default_storage
    from apps.files.models import FileModel
    settings.MEDIA_ROOT = str(tmp_path)
    data = b'A' * 262144
    started = admin_client.post('/api/v1/files/uploads/',
        {'name': 'winner.txt', 'total_size': len(data), 'chunk_size': len(data)}, format='json')
    identifier = started.data['data']['id']
    assert admin_client.put(f'/api/v1/files/uploads/{identifier}/chunks/0/', data,
        content_type='application/octet-stream', HTTP_X_CHUNK_SHA256=hashlib.sha256(data).hexdigest()).status_code == 200
    original, first = default_storage.open, True
    def open_chunk(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            assert admin_client.post(f'/api/v1/files/uploads/{identifier}/complete/', format='json').status_code == 200
            raise FileNotFoundError('concurrent winner removed its chunks')
        return original(*args, **kwargs)
    monkeypatch.setattr(default_storage, 'open', open_chunk)
    assert admin_client.post(f'/api/v1/files/uploads/{identifier}/complete/', format='json').status_code == 200
    assert FileModel.objects.count() == 1
    assert len([file for file in tmp_path.rglob('*') if file.is_file()]) == 1


def test_poison_notification_stops_retrying_and_releases_batch_for_valid_event(admin_user):
    from apps.core.tasks import dispatch_outbox
    from apps.notifications.models import Notification
    bad = OutboxEvent.objects.create(topic='notification.created', event_key='poison', available_at=timezone.now(), payload={'recipient_ids': ['invalid']})
    good = OutboxEvent.objects.create(topic='notification.created', event_key='valid', available_at=timezone.now(), payload={'recipient_ids': [str(admin_user.pk)], 'title': '有效通知'})
    for _ in range(6):
        OutboxEvent.objects.filter(pk__in=[bad.pk, good.pk]).update(available_at=timezone.now() - timedelta(seconds=1))
        dispatch_outbox(limit=1)
    bad.refresh_from_db(); good.refresh_from_db()
    assert bad.attempts == 5 and good.status == 'succeeded'
    assert Notification.objects.filter(recipient=admin_user, title='有效通知').exists()


def test_notification_detail_never_marks_another_recipient_read(admin_client, member_user):
    from apps.notifications.models import Notification
    row = Notification.objects.create(recipient=member_user, title='私有通知')
    assert admin_client.get(f'/api/v1/notifications/{row.pk}/?scope=all').status_code == 200
    row.refresh_from_db(); assert row.is_read is False
    assert admin_client.post(f'/api/v1/notifications/{row.pk}/mark_read/?scope=all').status_code == 404


def test_user_cannot_disable_or_delete_own_account(admin_client, admin_user):
    assert admin_client.patch(f'/api/v1/users/{admin_user.pk}/', {'version': 1, 'is_active': False}, format='json').status_code == 403
    assert admin_client.delete(f'/api/v1/users/{admin_user.pk}/').status_code == 403
    assert admin_client.post('/api/v1/users/bulk_action/', {'user_ids': [str(admin_user.pk)], 'action': 'deactivate'}, format='json').status_code == 403
    admin_user.refresh_from_db(); assert admin_user.is_active


@pytest.mark.parametrize('bulk', [False, True])
def test_django_admin_cannot_delete_current_user(client, admin_user, bulk):
    client.force_login(admin_user)
    url = '/admin/auth_app/user/' if bulk else f'/admin/auth_app/user/{admin_user.pk}/delete/'
    response = client.post(url, {'post': 'yes', 'action': 'delete_selected', '_selected_action': [str(admin_user.pk)]})
    assert response.status_code == 403
    assert User.objects.filter(pk=admin_user.pk, is_active=True).exists()


def test_django_admin_invalid_delete_id_does_not_fail_lock_query(client, admin_user):
    client.force_login(admin_user)
    assert client.post('/admin/auth_app/user/not-a-uuid/delete/', {'post': 'yes'}).status_code == 302


def test_menu_permission_and_parent_deletion_cannot_make_children_public():
    from apps.permissions.models import Permission, Menu
    permission = Permission.objects.create(code='test:read', name='测试', resource='test', action='read')
    parent = Menu.objects.create(name='父菜单', path='/parent', permission=permission)
    child = Menu.objects.create(name='子菜单', path='/child', parent=parent)
    for row in (permission, parent):
        with pytest.raises(ProtectedError), transaction.atomic(): row.delete()
    assert Menu.objects.get(pk=parent.pk).permission_id == permission.pk
    assert Menu.objects.filter(pk=child.pk).exists()


def test_password_change_wrong_old_password_is_rate_limited(admin_client):
    payload = {'old_password': 'incorrect', 'new_password': 'New-valid-password#909', 'new_password2': 'New-valid-password#909'}
    statuses = [admin_client.post('/api/v1/auth/change_password/', payload, format='json').status_code for _ in range(7)]
    assert statuses[:5] == [400] * 5
    assert statuses[5:] == [429, 429]


def test_throttles_ignore_forwarded_header_from_untrusted_peer(settings):
    from apps.auth_app.throttling import LoginRateThrottle, TrustedAnonRateThrottle
    settings.ADMINCORE_TRUSTED_PROXIES = []
    requests = [RequestFactory().post('/', REMOTE_ADDR='203.0.113.2', HTTP_X_FORWARDED_FOR=value)
                for value in ('1.1.1.1', '2.2.2.2', '3.3.3.3')]
    for throttle in (LoginRateThrottle(), TrustedAnonRateThrottle()):
        assert {throttle.get_ident(request) for request in requests} == {'203.0.113.2'}


def test_compose_proxy_host_resolves_only_explicit_direct_peer(settings, monkeypatch):
    from apps.core import client_ip
    settings.ADMINCORE_TRUSTED_PROXIES = []
    settings.ADMINCORE_TRUSTED_PROXY_HOSTS = ('frontend',)
    client_ip._proxy_addresses.cache_clear()
    monkeypatch.setattr(client_ip.socket, 'getaddrinfo', lambda *args, **kwargs: [(2, 1, 6, '', ('172.20.0.5', 0))])
    assert client_ip.request_ip(RequestFactory().get('/', REMOTE_ADDR='172.20.0.5', HTTP_X_FORWARDED_FOR='203.0.113.8')) == '203.0.113.8'
    assert client_ip.request_ip(RequestFactory().get('/', REMOTE_ADDR='172.20.0.6', HTTP_X_FORWARDED_FOR='203.0.113.8')) == '172.20.0.6'
    client_ip._proxy_addresses.cache_clear()


def test_admin_can_repair_disabled_current_step_with_version_and_audit(admin_user, member_user):
    reviewer, replacement = User.objects.create_user('disabled-reviewer'), User.objects.create_user('repair-reviewer')
    row = application(admin_user, member_user, reviewer)
    reviewer.is_active = False; reviewer.save(update_fields=['is_active'])
    step = row.steps.get()
    payload = {'target_user_id': str(replacement.pk), 'step_id': str(step.pk), 'expected_version': step.version}
    assert client(member_user).post(f'/api/v1/approvals/{row.pk}/repair-step/', payload, format='json').status_code == 403
    admin = client(admin_user)
    assert admin.get('/api/v1/approvals/?box=exceptions').data['data']['pagination']['total'] == 1
    response = admin.post(f'/api/v1/approvals/{row.pk}/repair-step/', payload, format='json')
    assert response.status_code == 200, response.content
    step.refresh_from_db(); assert step.assignee == replacement and step.version == 2
    assert row.actions.filter(action='transfer', target_user=replacement).exists()
    assert client(replacement).post(f'/api/v1/approvals/{row.pk}/approve/', format='json').status_code == 200


def test_form_detail_requires_record_read_even_for_owner(settings, admin_user, member_user):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'online_forms')
    settings.ROOT_URLCONF = 'tests.online_forms_urls'
    from apps.online_forms.models import OnlineForm, OnlineFormRecord
    form = OnlineForm.objects.create(code='private-detail', name='私有', status='published', created_by=admin_user, definition={'fields': []})
    row = OnlineFormRecord.objects.create(form=form, form_version=1, owner=member_user, data={})
    assert client(member_user).get(f'/api/v1/online-forms/private-detail/records/{row.pk}/').status_code == 403


def test_read_acl_does_not_grant_recycle_access(admin_user, member_user):
    from tests.test_file_acl import file_for
    from tests.file_permissions import grant_files
    from apps.files.models import FileAccessGrant
    row = file_for(admin_user)
    grant_files(member_user, 'file:recycle')
    grant = FileAccessGrant.objects.create(file=row, user=member_user, access_level='read')
    row.soft_delete(actor=admin_user)
    actor = client(member_user)
    assert actor.get('/api/v1/files/recycle/').data['data']['items'] == []
    grant.access_level = 'manage'; grant.save(update_fields=['access_level'])
    assert len(actor.get('/api/v1/files/recycle/').data['data']['items']) == 1


def test_expired_notification_cleanup_deletes_in_bounded_batches(admin_user, monkeypatch):
    from apps.notifications.models import Notification
    from apps.tasks.tasks import cleanup_expired_notifications
    from django.db.models.query import QuerySet
    old = timezone.now() - timedelta(days=400)
    Notification.objects.bulk_create([Notification(recipient=admin_user, title='过期', is_read=True, read_at=old) for _ in range(1001)])
    Notification.objects.create(recipient=admin_user, title='未读', is_read=False)
    Notification.objects.create(recipient=admin_user, title='新读', is_read=True, read_at=timezone.now())
    batches, original = [], QuerySet.delete
    def delete(queryset):
        if queryset.model is Notification:
            batches.append(queryset.count())
        return original(queryset)
    monkeypatch.setattr(QuerySet, 'delete', delete)
    result = cleanup_expired_notifications()
    assert result['deleted_notifications'] == 1001
    assert batches == [500, 500, 1] and Notification.objects.count() == 2


@pytest.mark.parametrize('payload', [
    {'comment': 'x' * 4001}, {'user_ids': ['00000000-0000-0000-0000-000000000001'] * 101},
    {'extra_data': {'payload': 'x' * 17000}},
])
def test_approval_payload_limits_are_rejected(admin_client, admin_user, payload):
    if 'extra_data' in payload:
        response = admin_client.post('/api/v1/approvals/', {'title': '有界', 'content': '正文', 'assignee_id': str(admin_user.pk), **payload}, format='json')
    else:
        response = admin_client.post('/api/v1/approvals/00000000-0000-0000-0000-000000000001/cc/', payload, format='json')
    assert response.status_code == 400


def test_advanced_approval_targets_obey_actor_scope(admin_user, member_user):
    from apps.core.models import DataScopeGrant
    from apps.permissions.models import Role, UserRole
    role = Role.objects.create(name='approval-self-only')
    UserRole.objects.create(user=member_user, role=role)
    DataScopeGrant.objects.create(role=role, resource='user', scope='self')
    row = application(admin_user, admin_user, member_user)
    outsider = User.objects.create_user('outside-approval-scope')
    actor = client(member_user)
    for action in ['add-sign', 'delegate', 'transfer', 'cc']:
        payload = {'user_ids': [str(outsider.pk)]} if action == 'cc' else {'target_user_id': str(outsider.pk)}
        assert actor.post(f'/api/v1/approvals/{row.pk}/{action}/', payload, format='json').status_code == 400
    assert row.steps.get().assignee == member_user and not row.cc_recipients.exists()


def test_initialize_runtime_database_wait_is_bounded_and_failure_stops_bootstrap(monkeypatch):
    from apps.core.management.commands import initialize_runtime
    from django.core.management.base import CommandError
    from django.db import OperationalError
    command = initialize_runtime.Command()
    with patch.object(initialize_runtime.connection, 'ensure_connection', side_effect=OperationalError('synthetic')):
        with patch.object(initialize_runtime.time, 'monotonic', side_effect=[0, 2]):
            with pytest.raises(CommandError, match='等待数据库超时'):
                command.handle(timeout=1, bootstrap=True)
    with patch.object(initialize_runtime, 'call_command', side_effect=CommandError('migration failed')) as called:
        with pytest.raises(CommandError, match='migration failed'):
            command.handle(timeout=1, bootstrap=True)
    called.assert_called_once_with('migrate', interactive=False)
