"""权限/范围/租约及 ASGI 协议单测；真实 Gunicorn/Nginx 另由验收脚本覆盖。"""
import asyncio
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.auth_app.sessions import issue_session
from apps.core import realtime
from apps.core.models import RealtimeLease, DataScopeGrant
from apps.core.modules import resolve_modules
from apps.notifications.models import Notification
from apps.permissions.models import Role, Permission, RolePermission, UserRole
from apps.tasks.models import TaskRecord
from apps.approvals.models import ApprovalRequest

pytestmark = pytest.mark.django_db
MODULES = ('notifications', 'tasks', 'approvals', 'realtime')


def token(user):
    return str(issue_session(user).access_token)


@override_settings(ADMINCORE_MODULES=MODULES)
def test_private_topics_and_task_permission_fresh(member_user, admin_user):
    raw = token(member_user)
    lease = realtime.acquire(raw)
    Notification.objects.create(recipient=member_user, title='私密正文')
    Notification.objects.create(recipient=admin_user, title='其他人不可见')
    ApprovalRequest.objects.create(applicant=admin_user, assignee=member_user, title='只给参与人')
    ApprovalRequest.objects.create(applicant=admin_user, assignee=admin_user, title='其他审批')
    TaskRecord.objects.create(creator=member_user, name='本人任务', status='running', progress=37, error='私密错误')
    TaskRecord.objects.create(creator=admin_user, name='其他任务', status='running')
    role = Role.objects.create(name='Realtime Self')
    UserRole.objects.create(user=member_user, role=role)
    result = realtime.snapshot(raw, lease)
    assert result['notifications']['total'] == result['notifications']['unread_count'] == 1
    assert result['approvals']['total'] == result['approvals']['todo_count'] == 1
    assert 'tasks' not in result
    permission = Permission.objects.create(name='任务只读', code='task:read', resource='task', action='read')
    RolePermission.objects.create(role=role, permission=permission)
    DataScopeGrant.objects.create(role=role, resource='task', scope='self')
    result = realtime.snapshot(raw, lease)
    assert result['tasks']['total'] == result['tasks']['active_count'] == 1
    assert result['tasks']['active'][0]['progress'] == 37
    assert all(secret not in json.dumps(result, ensure_ascii=False) for secret in ['私密', '本人任务', '其他任务', 'password', 'email', 'session'])
    role.is_active = False
    role.save(update_fields=['is_active'])
    assert 'tasks' not in realtime.snapshot(raw, lease)


@override_settings(ADMINCORE_MODULES=MODULES)
def test_one_session_limit_and_expiry_old_finally_cannot_release_new(member_user):
    raw = token(member_user)
    previous = realtime.acquire(raw)
    with pytest.raises(realtime.ConnectionLimit):
        realtime.acquire(raw)
    RealtimeLease.objects.filter(pk=previous).update(expires_at=timezone.now()-timedelta(seconds=1))
    current = realtime.acquire(raw)
    realtime.release(previous)
    assert RealtimeLease.objects.filter(pk=current).exists()
    with pytest.raises(AuthenticationFailed):
        realtime.snapshot(raw, previous)
    realtime.release(current)
    assert not RealtimeLease.objects.exists()


@override_settings(ADMINCORE_MODULES=MODULES)
def test_user_and_global_cap_bounded(member_user, admin_user):
    leases = [realtime.acquire(token(member_user)) for _ in range(3)]
    with pytest.raises(realtime.ConnectionLimit):
        realtime.acquire(token(member_user))
    with patch.object(realtime, 'MAX_CONNECTIONS', 3):
        with pytest.raises(realtime.ConnectionLimit):
            realtime.acquire(token(admin_user))
    assert RealtimeLease.objects.count() == 3
    for lease in leases:
        realtime.release(lease)


@pytest.mark.parametrize('change', ['device', 'version', 'password', 'disabled', 'force_password'])
@override_settings(ADMINCORE_MODULES=MODULES)
def test_live_connection_revocation_and_password_guard(member_user, change):
    raw = token(member_user)
    lease = realtime.acquire(raw)
    if change == 'device':
        from apps.auth_app.models import AuthSession
        AuthSession.objects.filter(pk=RealtimeLease.objects.get(pk=lease).session_id).update(revoked_at=timezone.now())
    else:
        if change == 'version': member_user.session_version += 1
        if change == 'password': member_user.set_password('A-new-fixture-password')
        if change == 'disabled': member_user.is_active = False
        if change == 'force_password': member_user.must_change_password = True
        member_user.save()
    with pytest.raises((AuthenticationFailed, PermissionDenied)):
        realtime.snapshot(raw, lease)
    with pytest.raises((AuthenticationFailed, PermissionDenied)):
        realtime.acquire(raw)


def test_all_presets_off_and_realtime_only_minimal_without_dependencies():
    for preset in ('minimal', 'standard', 'demo'):
        assert 'realtime' not in resolve_modules(preset)
    assert resolve_modules('minimal', 'realtime') == ('realtime',)


@override_settings(ADMINCORE_MODULES=MODULES)
def test_disabled_topics_do_not_read_business_tables(member_user):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    raw = token(member_user)
    lease = realtime.acquire(raw)
    with override_settings(ADMINCORE_MODULES=('realtime',)), CaptureQueriesContext(connection) as queries:
        assert realtime.snapshot(raw, lease) == {}
    assert all(not any(table in query['sql'] for table in ['notifications_notification', 'tasks_taskrecord', 'approvals_approvalrequest']) for query in queries)
    with override_settings(ADMINCORE_MODULES=()):
        with pytest.raises(PermissionDenied): realtime.snapshot(raw, lease)


def _asgi(scope, *, acquire=None, snapshot=None, disconnect_on_body=True, request_body=b''):
    from config.realtime_asgi import application, _policy_acquire, _policy_snapshot
    async def run():
        output = []
        disconnect = asyncio.Event()
        first = True
        async def receive():
            nonlocal first
            if first:
                first = False
                return {'type': 'http.request', 'body': request_body, 'more_body': False}
            await disconnect.wait()
            return {'type': 'http.disconnect'}
        async def send(message):
            output.append(message)
            if message['type'] == 'http.response.body' and disconnect_on_body:
                disconnect.set()
        with patch('config.realtime_asgi.database') as db:
            async def execute(function, *args):
                if function in (realtime.acquire, _policy_acquire):
                    if isinstance(acquire, Exception): raise acquire
                    return acquire
                if function in (realtime.snapshot, _policy_snapshot):
                    if isinstance(snapshot, Exception): raise snapshot
                    return snapshot or {}
            db.side_effect = execute
            await asyncio.wait_for(application(scope, receive, send), 1)
            called = [call.args for call in db.call_args_list]
        return output, called
    return asyncio.run(run())


def scope(**extra):
    return {'type': 'http', 'path': '/api/v1/realtime/events/', 'method': 'GET', 'query_string': b'',
            'scheme': 'http', 'headers': [(b'host', b'localhost'), (b'authorization', b'Bearer fixture')], **extra}


@pytest.mark.parametrize('extra,status', [({'query_string': b'token=private'}, 400), ({'method': 'POST'}, 405),
    ({'path': '/api/v1/users/'}, 404), ({'headers': [(b'host', b'evil.example')]}, 400),
    ({'headers': [(b'host', b'localhost')]}, 401),
    ({'headers': [(b'host', b'localhost'), (b'origin', b'https://evil.example')]}, 400),
    ({'headers': [(b'host', b'localhost'), (b'authorization', b'Bearer one'), (b'authorization', b'Bearer two')]}, 400)])
@override_settings(ADMINCORE_MODULES=MODULES)
def test_asgi_rejects_invalid_request_without_db(extra, status):
    output, calls = _asgi(scope(**extra))
    assert output[0]['status'] == status and not calls
    assert b'private' not in output[-1]['body'] and b'token' not in output[-1]['body']


@override_settings(ADMINCORE_MODULES=MODULES)
def test_asgi_frame_privacy_disconnect_and_release():
    output, calls = _asgi(scope(), acquire='lease', snapshot={'notifications': {'unread_count': 1}})
    assert output[0]['status'] == 200
    assert dict(output[0]['headers'])[b'cache-control'] == b'private, no-store'
    assert b'event: snapshot\n' in output[1]['body'] and b'id: 1\n' in output[1]['body']
    assert b'fixture' not in output[1]['body']
    assert calls[-1] == (realtime.release, 'lease')


@override_settings(ADMINCORE_MODULES=MODULES)
def test_asgi_revoked_does_not_emit_stale_snapshot():
    output, calls = _asgi(scope(), acquire='lease', snapshot=PermissionDenied('私密错误不回显'))
    assert b'access_revoked' in output[1]['body'] and '私密' not in output[1]['body'].decode()
    assert calls[-1] == (realtime.release, 'lease')


@override_settings(ADMINCORE_MODULES=())
def test_asgi_disabled_without_authentication_or_database():
    output, calls = _asgi(scope())
    assert output[0]['status'] == 404 and not calls


@override_settings(ADMINCORE_MODULES=MODULES)
def test_asgi_rejects_body_before_acquiring_budget():
    output, calls = _asgi(scope(), request_body=b'private')
    assert output[0]['status'] == 400 and not calls


@pytest.mark.parametrize('error,status', [(AuthenticationFailed('private'), 401), (realtime.ConnectionLimit(), 429), (RuntimeError('private'), 503)])
@override_settings(ADMINCORE_MODULES=MODULES)
def test_asgi_initial_auth_capacity_and_db_failure_safe(error, status):
    output, calls = _asgi(scope(), acquire=error)
    assert output[0]['status'] == status and b'private' not in output[-1]['body']
    assert not any(call[0] is realtime.release for call in calls)


@override_settings(ADMINCORE_MODULES=MODULES)
def test_asgi_snapshot_failure_safe_and_releases_budget():
    output, calls = _asgi(scope(), acquire='lease', snapshot=RuntimeError('private db error'))
    assert output[0]['status'] == 200 and b'unavailable' in output[1]['body']
    assert b'private db error' not in output[1]['body'] and calls[-1] == (realtime.release, 'lease')


@override_settings(ADMINCORE_MODULES=MODULES)
def test_asgi_burst_serializes_admission_without_serializing_streams():
    """同一事件循环的多个真实调用不能把预算事务同时压入线程池。"""
    from config.realtime_asgi import application, _policy_acquire, _policy_snapshot

    async def run():
        active = peak = snapshots = 0
        released = []
        all_streaming = asyncio.Event()

        async def database(function, *args):
            nonlocal active, peak, snapshots
            if function is _policy_acquire:
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(.01)
                active -= 1
                return args[0]
            if function is _policy_snapshot:
                snapshots += 1
                if snapshots == 8:
                    all_streaming.set()
                return {}
            released.append(args[0])

        async def client(index):
            first = True
            async def receive():
                nonlocal first
                if first:
                    first = False
                    return {'type': 'http.request', 'body': b''}
                await all_streaming.wait()
                return {'type': 'http.disconnect'}
            async def send(message):
                pass
            await application(scope(headers=[(b'host', b'localhost'),
                (b'authorization', f'Bearer fixture-{index}'.encode())]), receive, send)

        with patch('config.realtime_asgi.database', side_effect=database):
            await asyncio.wait_for(asyncio.gather(*(client(index) for index in range(8))), 2)
        assert peak == 1
        assert snapshots == len(released) == 8

    asyncio.run(run())


@override_settings(ADMINCORE_MODULES=MODULES)
@pytest.mark.parametrize('cancel_waiter', [False, True])
def test_asgi_admission_wait_is_bounded_and_recovers(cancel_waiter):
    from config import realtime_asgi as app

    async def run():
        started, finish = asyncio.Event(), asyncio.Event()
        called = []
        async def database(function, raw, *args):
            called.append(raw)
            if raw == 'first':
                started.set()
                await finish.wait()
            return raw
        with patch.object(app, 'database', side_effect=database), patch.object(app, 'ADMISSION_WAIT_SECONDS', .02):
            first = asyncio.create_task(app._admit('first', None))
            await started.wait()
            if cancel_waiter:
                queued = asyncio.create_task(app._admit('queued', None))
                await asyncio.sleep(0)
                queued.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await queued
            else:
                with pytest.raises(app.AdmissionUnavailable):
                    await app._admit('queued', None)
            finish.set()
            assert await first == 'first'
            assert await app._admit('after', None) == 'after'
        assert called == ['first', 'after']
    asyncio.run(run())


@override_settings(ADMINCORE_MODULES=MODULES)
def test_asgi_admission_queue_limit_recovers_across_event_loops():
    from config import realtime_asgi as app

    async def run():
        started, finish = asyncio.Event(), asyncio.Event()
        async def database(function, raw, *args):
            if raw == 'first':
                started.set()
                await finish.wait()
            return raw
        with patch.object(app, 'database', side_effect=database), patch.object(realtime, 'MAX_CONNECTIONS', 2):
            first = asyncio.create_task(app._admit('first', None))
            await started.wait()
            second = asyncio.create_task(app._admit('second', None))
            await asyncio.sleep(0)
            with pytest.raises(realtime.ConnectionLimit):
                await app._admit('overflow', None)
            finish.set()
            assert await asyncio.gather(first, second) == ['first', 'second']
            assert await app._admit('after', None) == 'after'
    for _ in range(2):
        asyncio.run(run())


@override_settings(ADMINCORE_MODULES=MODULES)
def test_asgi_cancelled_admission_waits_for_sql_and_releases_lease():
    from config import realtime_asgi as app

    async def run():
        started, finish, next_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
        released = []
        async def database(function, raw, *args):
            if function is realtime.release:
                released.append(raw)
                return
            if raw == 'first':
                started.set()
                await finish.wait()
            else:
                next_started.set()
            return raw
        with patch.object(app, 'database', side_effect=database):
            first = asyncio.create_task(app._admit('first', None))
            await started.wait()
            first.cancel()
            second = asyncio.create_task(app._admit('second', None))
            await asyncio.sleep(.01)
            assert not next_started.is_set()
            finish.set()
            with pytest.raises(asyncio.CancelledError):
                await first
            assert await second == 'second'
        assert released == ['first']
    asyncio.run(run())
