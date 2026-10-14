"""公告格式兼容、内容限制、状态转换及旧缓存读取回归。"""
from unittest.mock import patch

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from rest_framework.exceptions import ValidationError

from apps.core.models import IdempotencyRecord
from apps.logs.models import OperationLog
from apps.notifications.announcement_content import prepare_content, sanitize_html
from apps.notifications.models import Announcement

MANAGE = '/api/v1/notifications/announcements/manage/'
PUBLIC = '/api/v1/notifications/announcements/'


def create(client, **extra):
    return client.post(MANAGE, {'title': '格式公告', 'content': '正文', 'version': 0, **extra}, format='json')


@pytest.mark.django_db
def test_plain_default_preserves_original_text_and_markup(admin_client, member_client):
    content = '  <script>literal text</script>\n&copy;  '
    response = create(admin_client, content=content)
    assert response.status_code == 201
    data = response.data['data']
    assert data['content_format'] == 'plain' and data['content'] == content
    assert Announcement.objects.get(pk=data['id']).content == content
    assert admin_client.post(f'{MANAGE}{data["id"]}/publish/', {'version': 1}, format='json').status_code == 200
    assert member_client.get(f'{PUBLIC}{data["id"]}/').data['data']['content'] == content


@pytest.mark.django_db
def test_html_create_edit_keeps_format_when_omitted_then_explicit_plain(admin_client):
    content = '<p class="bad">正文<strong>强调</strong><script>private-secret</script></p>'
    response = create(admin_client, content=content, content_format='html')
    assert response.status_code == 201
    data = response.data['data']
    assert data['content'] == '<p>正文<strong>强调</strong></p>' and data['content_format'] == 'html'
    url = f'{MANAGE}{data["id"]}/'
    edit = admin_client.patch(url, {'title': '更新', 'content': '<h2 onclick="bad">标题</h2>', 'version': 1}, format='json')
    assert edit.status_code == 200
    assert edit.data['data']['content_format'] == 'html' and edit.data['data']['content'] == '<h2>标题</h2>'
    plain = admin_client.patch(url, {'title': '文字', 'content': '<em>literal</em>', 'content_format': 'plain', 'version': 2}, format='json')
    assert plain.status_code == 200 and plain.data['data']['content'] == '<em>literal</em>'
    log = OperationLog.objects.filter(resource='announcement', resource_id=data['id']).first()
    assert 'content_format' in log.description and 'private-secret' not in log.description and '正文' not in log.description


@pytest.mark.django_db
@pytest.mark.parametrize('data', [{'content_format': 'markdown'}, {'content_format': None}, {'unlisted': 'value'},
                                 {'content': '<p>&nbsp;<br>\u200b</p>', 'content_format': 'html'},
                                 {'content': '<script>secret</script>', 'content_format': 'html'},
                                 {'content': 'x' * 20001, 'content_format': 'html'}, {'content': ' \n\t '},
                                 {'content': '&' * 5000, 'content_format': 'html'}])
def test_invalid_empty_or_expanded_content_no_write(admin_client, data):
    assert create(admin_client, **data).status_code == 400
    assert not Announcement.objects.exists()


@pytest.mark.django_db
def test_read_and_publish_sanitize_raw_legacy_html_without_leaking(admin_client, member_client):
    row = Announcement.objects.create(title='旧行', content='<p>正文<script>private-secret</script></p>', content_format='html')
    assert admin_client.get(f'{MANAGE}{row.pk}/').data['data']['content'] == '<p>正文</p>'
    row.refresh_from_db()
    assert 'private-secret' in row.content  # 读取无副作用，发布时净化持久正文。
    response = admin_client.post(f'{MANAGE}{row.pk}/publish/', {'version': 1}, format='json')
    assert response.status_code == 200
    row.refresh_from_db()
    assert row.content == '<p>正文</p>'
    assert member_client.get(PUBLIC).data['data']['items'][0]['content'] == '<p>正文</p>'
    Announcement.objects.filter(pk=row.pk).update(content='<svg>hidden</svg>')
    response = admin_client.post(f'{MANAGE}{row.pk}/withdraw/', {'version': 2}, format='json')
    assert response.status_code == 200 and response.data['data']['content'] == ''
    assert admin_client.post(f'{MANAGE}{row.pk}/publish/', {'version': 3}, format='json').status_code == 400


@pytest.mark.django_db
def test_cached_idempotent_html_is_sanitized_on_replay(admin_client):
    body = {'title': '缓存', 'content': '<p>安全</p>', 'content_format': 'html', 'version': 0}
    first = admin_client.post(MANAGE, body, format='json', HTTP_IDEMPOTENCY_KEY='html-cache-once')
    assert first.status_code == 201
    record = IdempotencyRecord.objects.get(key='html-cache-once')
    record.response_data['data']['content'] = '<p>安全<script>private-cache-secret</script></p>'
    record.save(update_fields=['response_data'])
    replay = admin_client.post(MANAGE, body, format='json', HTTP_IDEMPOTENCY_KEY='html-cache-once')
    assert replay.status_code == 201 and replay['Idempotency-Replayed'] == 'true'
    assert replay.data['data']['content'] == '<p>安全</p>'
    assert Announcement.objects.count() == 1


@pytest.mark.django_db
def test_sanitizer_exception_is_fixed_503_and_rolls_back(admin_client):
    with patch('apps.notifications.announcement_content.nh3.clean', side_effect=RuntimeError('private-body-secret')):
        response = create(admin_client, content='<p>body</p>', content_format='html')
    assert response.status_code == 503 and 'private-body-secret' not in str(response.data)
    assert not Announcement.objects.exists()


@pytest.mark.django_db
def test_database_rejects_unknown_format():
    with pytest.raises(IntegrityError), transaction.atomic():
        Announcement.objects.create(title='bad', content='body', content_format='unknown')


def test_sanitizer_is_idempotent_and_plain_not_html():
    content = '<h2>标题</h2><p><a href="https://example.com/a">链接</a><code>&lt;b&gt;</code></p>'
    clean = sanitize_html(content)
    assert sanitize_html(clean) == clean
    assert 'rel="noopener noreferrer nofollow"' in clean
    assert prepare_content(content, 'plain') == content
    with pytest.raises(ValidationError):
        prepare_content('', 'html')


@pytest.mark.django_db(transaction=True)
def test_migration_preserves_existing_content_as_plain():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old_target = [('notifications', '0003_announcement')]
    try:
        executor.migrate(old_target)
        old_apps = executor.loader.project_state(old_target).apps
        old_model = old_apps.get_model('notifications', 'Announcement')
        content = '<script>this was always plain text</script>'
        old = old_model.objects.create(title='旧公告', content=content)
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        row = Announcement.objects.get(pk=old.pk)
        assert row.content_format == 'plain' and row.content == content
    finally:
        MigrationExecutor(connection).migrate(latest)
