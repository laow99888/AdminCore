"""必须在 PostgreSQL 执行的并发回归；SQLite 不提供行锁。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import time
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection, connections
from rest_framework.test import APIClient

from apps.approvals.models import ApprovalFlow
from tests.test_audit_20261017_repairs import graph, application

pytestmark = [pytest.mark.django_db(transaction=True),
              pytest.mark.skipif(connection.vendor != 'postgresql', reason='需要 PostgreSQL 行锁')]
User = get_user_model()


def concurrent(*operations):
    barrier = Barrier(len(operations))
    def invoke(operation):
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
            barrier.wait(timeout=10)
            return operation()
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(invoke, operation) for operation in operations]
        return [future.result(timeout=30) for future in futures]


def request(actor, verb, url, payload):
    client = APIClient(); client.force_authenticate(User.objects.get(pk=actor))
    response = getattr(client, verb)(url, payload, format='json')
    assert response.status_code < 500, response.content
    return response.status_code


@pytest.mark.parametrize('resource', ['flow', 'form', 'report', 'record'])
def test_concurrent_stale_updates_have_one_winner(settings, admin_user, resource):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'online_forms', 'reports')
    settings.ROOT_URLCONF = 'tests.tenant_object_urls'
    from apps.online_forms.models import OnlineForm, OnlineFormRecord
    from apps.reports.models import ReportDefinition
    from apps.online_forms.validators import validate_definition
    field = validate_definition({'fields': [{'key': 'title', 'label': '标题', 'type': 'text'}]})
    if resource == 'record':
        form = OnlineForm.objects.create(code='concurrent', name='并发', status='published', created_by=admin_user, definition=field)
        row = OnlineFormRecord.objects.create(form=form, owner=admin_user, form_version=1, data={'title': '初始'})
        url, verb = f'/api/v1/online-forms/concurrent/records/{row.pk}/', 'patch'
        payload = {'version': 1, 'data': {'title': '更新'}}
    else:
        model, base, definition = {
            'form': (OnlineForm, '/api/v1/online-forms/forms/', field),
            'report': (ReportDefinition, '/api/v1/reports/definitions/', {'data_source': 'tasks', 'chart_type': 'table', 'metric': {'field': 'id', 'aggregation': 'count'}}),
            'flow': (ApprovalFlow, '/api/v1/approvals/flows/', graph(admin_user)),
        }[resource]
        row = model.objects.create(code='concurrent', name='初始', created_by=admin_user, definition=definition)
        url, verb = base + str(row.pk) + '/', 'put' if resource == 'flow' else 'patch'
        payload = {'name': '更新', 'code': row.code, 'definition': definition, 'version': 1}
    second = admin_user if resource == 'record' else User.objects.create_superuser('second-editor', '', 'Isolated#Second7719')
    result = concurrent(lambda: request(admin_user.pk, verb, url, payload), lambda: request(second.pk, verb, url, payload))
    assert sorted(result) == [200, 409]
    row.refresh_from_db(); assert row.version == 2


def test_concurrent_add_sign_never_violates_unique_constraint(admin_user, member_user):
    row = application(admin_user, member_user, admin_user)
    target = User.objects.create_user('concurrent-target')
    url = f'/api/v1/approvals/{row.pk}/add-sign/'
    result = concurrent(*[lambda: request(admin_user.pk, 'post', url, {'target_user_id': str(target.pk)}) for _ in range(2)])
    assert sorted(result) == [200, 409]
    assert row.steps.filter(assignee=target).count() == 1


def test_concurrent_admin_self_demotion_preserves_one_admin(admin_user):
    other = User.objects.create_user('other-admin', is_staff=True)
    def demote(user):
        from apps.users.safety import lock_management_users, protect_management_access
        from django.db import transaction
        from django.core.exceptions import PermissionDenied
        try:
            with transaction.atomic():
                rows = lock_management_users([user.pk])
                current = next(row for row in rows if row.pk == user.pk)
                protect_management_access(current, [current], values={'is_staff': False, 'is_superuser': False})
                current.is_staff = current.is_superuser = False
                current.save(update_fields=['is_staff', 'is_superuser'])
            return 200
        except PermissionDenied:
            return 403
    assert sorted(concurrent(lambda: demote(admin_user), lambda: demote(other))) == [200, 403]
    assert User.objects.filter(is_active=True, is_staff=True).count() == 1


def test_initializer_serializes_migrations_across_connections():
    mutex, state = Lock(), {'active': 0, 'peak': 0, 'calls': 0}
    def migration(*args, **kwargs):
        with mutex:
            state['active'] += 1; state['calls'] += 1
            state['peak'] = max(state['peak'], state['active'])
        time.sleep(.1)
        with mutex:
            state['active'] -= 1
    with patch('apps.core.management.commands.initialize_runtime.call_command', migration):
        concurrent(*[lambda: call_command('initialize_runtime', timeout=10) for _ in range(2)])
    assert state == {'active': 0, 'peak': 1, 'calls': 2}


def test_concurrent_old_password_guesses_cannot_exceed_budget(admin_user):
    actor = APIClient()
    login = actor.post('/api/v1/auth/login/', {'username': 'admin', 'password': 'Admin#12345'}, format='json')
    access = login.data['access']
    payload = {'old_password': 'incorrect', 'new_password': 'Isolated#Replacement7719', 'new_password2': 'Isolated#Replacement7719'}
    def guess():
        client = APIClient(); client.credentials(HTTP_AUTHORIZATION='Bearer ' + access)
        return client.post('/api/v1/auth/change_password/', payload, format='json').status_code
    assert sorted(concurrent(*[guess for _ in range(7)])) == [400] * 5 + [429] * 2


def test_concurrent_upload_completion_keeps_one_object_without_storage_row_locks(admin_user, settings, tmp_path, monkeypatch):
    import hashlib
    from django.core.files.storage import default_storage
    from apps.files.models import FileModel
    settings.MEDIA_ROOT = str(tmp_path)
    data = b'x' * 262144
    client = APIClient(); client.force_authenticate(admin_user)
    response = client.post('/api/v1/files/uploads/',
        {'name': 'concurrent.txt', 'total_size': len(data), 'chunk_size': len(data)}, format='json')
    identifier = response.data['data']['id']
    assert client.put(f'/api/v1/files/uploads/{identifier}/chunks/0/', data,
        content_type='application/octet-stream', HTTP_X_CHUNK_SHA256=hashlib.sha256(data).hexdigest()).status_code == 200
    original = default_storage.save
    staged = Barrier(2)
    def save(name, content, *args, **kwargs):
        assert not connection.in_atomic_block
        result = original(name, content, *args, **kwargs)
        staged.wait(timeout=10)
        return result
    monkeypatch.setattr(default_storage, 'save', save)
    result = concurrent(*[lambda: request(admin_user.pk, 'post',
        f'/api/v1/files/uploads/{identifier}/complete/', {}) for _ in range(2)])
    assert result == [200, 200]
    assert FileModel.objects.count() == 1
    assert len([p for p in tmp_path.rglob('*') if p.is_file()]) == 1
