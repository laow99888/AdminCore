"""演示命令拒绝普通/生产目标，签名和令牌失败前不允许flush。"""
from contextlib import nullcontext
from io import StringIO
import secrets
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from apps.core import demo
from apps.core.models import BootstrapState
from apps.core.management.commands import demo_admincore as command

User = get_user_model()
MODULES = ('files', 'tasks', 'notifications', 'data_io', 'approvals', 'system', 'organization', 'example')


@pytest.fixture
def identity(monkeypatch, settings):
    instance = 'a' * 32
    token = 'b' * 64
    accounts = {name: secrets.token_urlsafe(40) for name in ('demo_admin', 'demo_editor', 'demo_viewer')}
    for key, value in {
        'DJANGO_ENV': 'demo', 'DB_NAME': 'admincore_demo_' + instance,
        'ADMINCORE_DEMO_INSTANCE': instance, 'ADMINCORE_DEMO_RESET_TOKEN': token,
        'ADMINCORE_ADMIN_USERNAME': 'demo_admin', 'ADMINCORE_ADMIN_PASSWORD': accounts['demo_admin'],
        'ADMINCORE_DEMO_EDITOR_PASSWORD': accounts['demo_editor'],
        'ADMINCORE_DEMO_VIEWER_PASSWORD': accounts['demo_viewer'],
    }.items():
        monkeypatch.setenv(key, value)
    settings.ADMINCORE_PRESET = 'demo'
    settings.ADMINCORE_MODULES = MODULES
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchone.return_value = ('admincore_demo_' + instance,)
    connection = SimpleNamespace(vendor='postgresql', settings_dict={'NAME': 'admincore_demo_' + instance},
                                 cursor=lambda: cursor)
    monkeypatch.setattr(demo, 'connection', connection)
    return instance, token, accounts, connection, cursor


def test_target_checks_actual_database_and_returns_bound_marker(identity):
    instance, token, accounts, connection, cursor = identity
    result = demo.validate_target()
    assert result[:2] == (instance, token) and result[3] == accounts
    assert result[2].startswith('demo-v1:') and len(result[2]) < 100
    cursor.execute.assert_called_once_with('SELECT current_database()')
    cursor.fetchone.return_value = ('admincore',)
    with pytest.raises(CommandError, match='实际数据库'):
        demo.validate_target()


@pytest.mark.parametrize('key,value', [
    ('DJANGO_ENV', 'production'), ('DJANGO_ENV', 'development'),
    ('DB_NAME', 'admincore'), ('ADMINCORE_DEMO_INSTANCE', '../outside'),
    ('ADMINCORE_DEMO_RESET_TOKEN', ''), ('ADMINCORE_ADMIN_USERNAME', 'admin'),
    ('ADMINCORE_ADMIN_PASSWORD', 'Admin#12345'), ('ADMINCORE_DEMO_EDITOR_PASSWORD', 'Demo#12345'),
])
def test_rejects_environment_mismatch_before_any_sql(identity, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(CommandError):
        demo.validate_target()
    identity[4].execute.assert_not_called()


@pytest.mark.parametrize('field,value', [('vendor', 'sqlite'), ('settings_dict', {'NAME': 'other'})])
def test_rejects_wrong_connection(identity, field, value):
    setattr(identity[3], field, value)
    with pytest.raises(CommandError):
        demo.validate_target()
    identity[4].execute.assert_not_called()


def test_rejects_non_demo_preset_and_remote_storage(identity, settings):
    settings.ADMINCORE_PRESET = 'standard'
    with pytest.raises(CommandError):
        demo.validate_target()
    settings.ADMINCORE_PRESET = 'demo'
    settings.ADMINCORE_STORAGE_BACKEND = 's3'
    with pytest.raises(CommandError):
        demo.validate_target()


@pytest.mark.django_db
@pytest.mark.parametrize('preset,explicit', [('standard', True), ('demo', False)])
def test_legacy_demo_never_creates_fixed_credentials(monkeypatch, settings, preset, explicit):
    monkeypatch.setenv('DJANGO_ENV', 'development')
    monkeypatch.delenv('ADMINCORE_DEMO_INSTANCE', raising=False)
    settings.ADMINCORE_PRESET = preset
    with pytest.raises(CommandError):
        call_command('bootstrap_admincore', demo=explicit, stdout=StringIO())
    assert not User.objects.exists() and not BootstrapState.objects.exists()


@pytest.fixture
def seed_context(identity, monkeypatch):
    # Only seed orchestration uses SQLite; the real target guard is tested above without a DB mutation.
    instance, token, marker, accounts = demo.validate_target()
    monkeypatch.setattr(command, 'validate_target', lambda: (instance, token, marker, accounts))
    monkeypatch.setattr(command, 'demo_lock', lambda _: nullcontext())
    return marker, token, accounts


@pytest.mark.django_db
def test_full_fixture_has_scope_roles_states_and_idempotent_initialization(seed_context):
    from apps.approvals.models import ApprovalRequest
    from apps.notifications.models import Announcement
    from apps.example.models import WorkItem
    from apps.files.models import FileModel
    from apps.permissions.models import RolePermission
    from apps.core.models import Department, DataScopeGrant
    output = StringIO()
    call_command('demo_admincore', stdout=output)
    assert User.objects.count() == 3 and User.objects.filter(is_superuser=True).count() == 1
    for username, password in seed_context[2].items():
        person = User.objects.get(username=username)
        assert person.check_password(password)
        assert not person.check_password('Admin#12345') and not person.check_password('Demo#12345')
        assert not person.must_change_password
    assert Department.objects.count() == 3 and WorkItem.objects.count() == 6
    assert set(ApprovalRequest.objects.values_list('status', flat=True)) == {'pending', 'approved', 'rejected'}
    assert set(Announcement.objects.values_list('status', flat=True)) == {'published', 'draft'}
    assert FileModel.objects.count() == 2 and FileModel.objects.filter(is_deleted=True).count() == 1
    for row in FileModel.objects.all():
        assert row.file.storage.exists(row.file.name)
    assert DataScopeGrant.objects.count() == 6
    assert not RolePermission.objects.filter(role__name__startswith='演示',
        permission__code__in=['user:create', 'user:update', 'user:delete', 'role:update']).exists()
    modified = WorkItem.objects.first()
    modified.title = '保留用户修改'
    modified.save()
    call_command('demo_admincore', stdout=output)
    assert WorkItem.objects.filter(title='保留用户修改').exists() and WorkItem.objects.count() == 6
    assert all(secret not in output.getvalue() for secret in seed_context[2].values())


@pytest.mark.django_db
def test_unmarked_existing_database_is_never_adopted(seed_context):
    User.objects.create_user('real-user', password='Fixture#98383')
    with pytest.raises(CommandError, match='拒绝接管'):
        call_command('demo_admincore', stdout=StringIO())
    assert list(User.objects.values_list('username', flat=True)) == ['real-user']


@pytest.mark.django_db
def test_bad_reset_token_and_foreign_marker_never_reach_flush(seed_context, monkeypatch):
    called = MagicMock()
    monkeypatch.setattr(command, 'call_command', called)
    with pytest.raises(CommandError, match='令牌'):
        call_command('demo_admincore', reset=True, confirm='wrong', stdout=StringIO())
    BootstrapState.objects.create(key='demo-v1:' + 'f' * 64)
    with pytest.raises(CommandError, match='签名演示标记'):
        call_command('demo_admincore', reset=True, confirm=seed_context[1], stdout=StringIO())
    called.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_reset_only_owned_fixture_and_removes_old_sessions(seed_context):
    from datetime import timedelta
    from django.utils import timezone
    from apps.auth_app.models import AuthSession
    from apps.example.models import WorkItem
    call_command('demo_admincore', stdout=StringIO())
    admin = User.objects.get(username='demo_admin')
    now = timezone.now()
    AuthSession.objects.create(user=admin, session_version=admin.session_version,
        password_hash='old', refresh_jti='old', created_at=now, last_seen_at=now,
        expires_at=now + timedelta(hours=1))
    User.objects.create_user('demo_created_user', password='Fixture#98383')
    old_admin = admin.pk
    call_command('demo_admincore', reset=True, confirm=seed_context[1], stdout=StringIO())
    assert User.objects.count() == 3 and not User.objects.filter(pk=old_admin).exists()
    assert not AuthSession.objects.exists() and WorkItem.objects.count() == 6
    assert BootstrapState.objects.filter(key=seed_context[0]).exists()


def test_duplicate_seed_lock_fails_closed(identity):
    cursor = identity[4]
    cursor.fetchone.return_value = (False,)
    with pytest.raises(CommandError, match='正在执行'):
        with demo.demo_lock(identity[0]):
            pytest.fail('must not enter')
    assert cursor.execute.call_args.args[0] == 'SELECT pg_try_advisory_lock(%s)'


@pytest.mark.django_db
def test_demo_template_and_png_can_be_previewed(seed_context):
    from rest_framework.test import APIClient
    from apps.files.models import FileModel
    from apps.files.preview import preview_content
    from apps.notifications.models import MessageTemplate

    call_command('demo_admincore', stdout=StringIO())
    client = APIClient()
    response = client.post('/api/v1/auth/login/', {'username': 'demo_admin',
        'password': seed_context[2]['demo_admin']}, format='json')
    assert response.status_code == 200
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.json()['access'])
    template = MessageTemplate.objects.get(code='demo-welcome')
    response = client.post('/api/v1/notifications/templates/' + str(template.pk) + '/preview/',
        {'revision': 1, 'values': {'name': '演示访客'}}, format='json')
    assert response.status_code == 200
    assert response.json()['data']['subject'] == '欢迎 演示访客'
    image = FileModel.objects.get(original_name='演示图片.png')
    content, mime = preview_content(image)
    assert mime == 'image/png' and content.startswith(b'\x89PNG\r\n\x1a\n')
    response = client.get('/api/v1/files/' + str(image.pk) + '/preview/')
    assert response.status_code == 200 and response['Content-Type'] == 'image/png'


@pytest.mark.django_db
def test_demo_accounts_login_read_own_items_and_cannot_grant_roles(seed_context, settings):
    from rest_framework.test import APIClient
    # config.urls may already be imported with the standard preset by earlier tests.
    settings.ROOT_URLCONF = 'tests.example_urls'
    call_command('demo_admincore', stdout=StringIO())
    for username in ('demo_editor', 'demo_viewer'):
        client = APIClient()
        response = client.post('/api/v1/auth/login/', {'username': username,
            'password': seed_context[2][username]}, format='json')
        assert response.status_code == 200
        assert not response.json()['user']['must_change_password']
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.json()['access'])
        response = client.get('/api/v1/example/items/')
        assert response.status_code == 200 and response.json()['data']['pagination']['total'] == 2
        assert all(row['title'].startswith(username) for row in response.json()['data']['items'])
        response = client.post('/api/v1/users/', {'username': 'forbidden'}, format='json')
        assert response.status_code == 403
