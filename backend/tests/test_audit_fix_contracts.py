"""集中审查修复的输入、时区、响应头、可信代理和查询预算回归。"""
from datetime import datetime
import ipaddress
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.response import Response

from apps.core.client_ip import request_ip
from apps.core.mixins import EnvelopeResponseMixin
from apps.logs.models import LoginLog, OperationLog
from apps.notifications.serializers import NotificationCreateSerializer
from apps.permissions.models import Menu
from tests.test_data_io import build_xlsx


@pytest.mark.parametrize('direct,forwarded,expected', [
    ('203.0.113.8', '192.0.2.7', '203.0.113.8'),
    ('10.0.0.5', '192.0.2.7', '192.0.2.7'),
    ('10.0.0.5', '192.0.2.7, 10.0.0.6', '192.0.2.7'),
    ('10.0.0.5', '192.0.2.7, 198.51.100.8', '198.51.100.8'),
    ('10.0.0.5', 'invalid', '10.0.0.5'),
    ('10.0.0.5', '192.0.2.7,', '10.0.0.5'),
    ('2001:db8:1::5', '2001:db8:2::8', '2001:db8:2::8'),
    ('invalid', '192.0.2.7', None),
])
def test_only_explicit_trusted_proxy_chain_is_used(settings, direct, forwarded, expected):
    settings.ADMINCORE_TRUSTED_PROXIES = tuple(map(ipaddress.ip_network, ['10.0.0.0/24', '2001:db8:1::/64']))
    assert request_ip(SimpleNamespace(META={'REMOTE_ADDR': direct, 'HTTP_X_FORWARDED_FOR': forwarded})) == expected


def test_envelope_keeps_transport_headers_and_cookies():
    response = Response({'id': 1}, status=201, headers={'Location': '/users/1/', 'ETag': 'abc', 'Retry-After': '10', 'Content-Length': '8'})
    response.set_cookie('example', 'synthetic', secure=True)
    original = response
    result = EnvelopeResponseMixin()._envelope(response)
    assert result is original and result.status_code == 201
    assert result['Location'] == '/users/1/' and result['ETag'] == 'abc' and result['Retry-After'] == '10'
    assert result.cookies['example']['secure'] and not result.has_header('Content-Length')
    assert result.data['data'] == {'id': 1}


@pytest.mark.django_db
@pytest.mark.parametrize('ids', [[], ['x'] * 1001, ['x', 'x'], 'x'])
def test_notification_rejects_bad_recipient_list_before_database_queries(ids):
    with CaptureQueriesContext(connection) as queries:
        serializer = NotificationCreateSerializer(data={'recipient_ids': ids, 'title': 'test'})
        assert not serializer.is_valid()
    assert len(queries) == 0


@pytest.mark.django_db
def test_upload_canonical_envelope_keeps_v1_legacy_fields(admin_client):
    from tests.test_files import make_file
    response = admin_client.post('/api/v1/files/', {'file': make_file('envelope.txt')}, format='multipart')
    assert response.status_code == 201
    body = response.json()
    assert body['code'] == 201 and body['data']['id'] == body['id']


@pytest.mark.django_db
def test_menu_tree_queries_do_not_grow_per_node(admin_client):
    parent = Menu.objects.create(name='Root', path='/')
    for index in range(4):
        Menu.objects.create(name=f'Node {index}', path=f'/audit-node-{index}', parent=parent)
    with CaptureQueriesContext(connection) as small:
        assert admin_client.get('/api/v1/permissions/menus/my_menu/').status_code == 200
    for index in range(20):
        Menu.objects.create(name=f'Extra {index}', path=f'/audit-extra-{index}', parent=parent)
    with CaptureQueriesContext(connection) as large:
        response = admin_client.get('/api/v1/permissions/menus/my_menu/')
    assert response.status_code == 200
    assert len(large) <= len(small) + 1
    assert len(response.json()['data'][0]['children']) == 24


@pytest.mark.django_db
@pytest.mark.parametrize('current', ['2026-10-16T02:00:00+00:00', '2027-01-01T02:00:00+00:00'])
def test_dashboard_uses_shanghai_midnight_for_counts_and_trend(admin_client, admin_user, current):
    from datetime import timedelta
    now = datetime.fromisoformat(current)
    admin_client.force_authenticate(admin_user)
    LoginLog.objects.all().delete()
    OperationLog.objects.all().delete()
    midnight = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    times = [midnight - timedelta(seconds=1), midnight, midnight + timedelta(hours=1), midnight + timedelta(days=1)]
    for moment in times:
        row = LoginLog.objects.create(user=admin_user, username=admin_user.username, status='success', ip_address='127.0.0.1')
        LoginLog.objects.filter(pk=row.pk).update(created_at=moment)
        row = OperationLog.objects.create(user=admin_user, action='read', resource='fixture', ip_address='127.0.0.1')
        OperationLog.objects.filter(pk=row.pk).update(created_at=moment)
    with patch('django.utils.timezone.now', return_value=now):
        data = admin_client.get('/api/v1/dashboard/stats/').json()['data']
    assert data['totals']['today_logins'] == data['totals']['today_operations'] == 2
    assert data['login_trend'][-1] == {'date': midnight.date().isoformat(), 'success': 2, 'failed': 0}
    assert data['login_trend'][-2]['success'] == 1
    assert len(data['login_trend']) == 7 and data['login_trend'][0]['success'] == 0


@pytest.mark.django_db
def test_import_invalid_model_fields_fail_per_row_and_continue(admin_client):
    from apps.data_io.tasks import run_data_import
    from apps.tasks.models import TaskRecord
    from django.contrib.auth import get_user_model
    content = build_xlsx([
        ['audit-valid-one', 'one@example.test', '', '', ''],
        ['invalid user!', 'two@example.test', '', '', ''],
        ['audit-long', 'long@example.test', 'x' * 151, '', ''],
        ['audit-valid-last', 'last@example.test', '', '', ''],
    ])
    response = admin_client.post('/api/v1/data-io/import/', {'file': content, 'resource': 'users'}, format='multipart')
    assert response.status_code == 200
    identifier = response.json()['data']['id']
    run_data_import(identifier)
    task = TaskRecord.objects.get(pk=identifier)
    assert task.status == 'success' and task.result['created'] == task.result['failed'] == 2
    users = get_user_model().objects.filter(username__startswith='audit-valid')
    assert users.count() == 2 and all(not user.has_usable_password() for user in users)
