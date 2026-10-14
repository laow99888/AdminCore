"""从 HTTP/存储边界独立验证富文本安全，不调用产品消毒函数作为断言。"""
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auth_app.models import AuthSession
from apps.auth_app.sessions import issue_session
from apps.logs.models import OperationLog
from apps.core.models import IdempotencyRecord
from apps.notifications.models import Announcement

pytestmark = pytest.mark.django_db
PUBLIC = '/api/v1/notifications/announcements/'
MANAGE = PUBLIC + 'manage/'
ALLOWED = {'p', 'br', 'h2', 'h3', 'strong', 'em', 'u', 's', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'hr', 'a'}


class SafeDocument(HTMLParser):
    def handle_starttag(self, tag, attrs):
        assert tag in ALLOWED, f'active or unsupported element: {tag}'
        attributes = dict(attrs)
        assert set(attributes) <= ({'href', 'rel'} if tag == 'a' else set())
        if 'href' in attributes:
            href = attributes['href']
            parsed = urlsplit(href)
            assert parsed.scheme in ('http', 'https') and parsed.hostname
            assert parsed.username is None and parsed.password is None
            assert not any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in href)
            assert set(attributes.get('rel', '').split()) == {'noopener', 'noreferrer', 'nofollow'}

    handle_startendtag = handle_starttag


def safe(content):
    parser = SafeDocument(convert_charrefs=True)
    parser.feed(content)
    parser.close()


def create(client, content, **extra):
    return client.post(MANAGE, {'title': '安全公告', 'content': content,
        'content_format': 'html', 'version': 0, **extra}, format='json')


ATTACKS = [
    '<p onclick="alert(1)" style="color:red" class="x" id="x" name="x">安全正文</p>',
    '<p>安全正文</p><img src="https://attacker.invalid/pixel" onerror="alert(1)">',
    '<p>安全正文</p><script>discard-script-marker</script>',
    '<p>安全正文</p><style>discard-style-marker</style>',
    '<p>安全正文</p><iframe srcdoc="<script>alert(1)</script>">discard-iframe-marker</iframe>',
    '<p>安全正文</p><svg><a href="javascript:alert(1)">discard-svg-marker</a></svg>',
    '<p>安全正文</p><math><mtext>discard-math-marker</mtext></math>',
    '<p>安全正文</p><!-- <img src=x onerror=alert(1)> --><input autofocus onfocus="alert(1)">',
    '<p>安全正文</p><form action="https://attacker.invalid"><button>click</button></form>',
    '<p>安全正文</p><a href="jav&#x61;script:alert(1)">unsafe</a>',
    '<p>安全正文</p><a href="data:text/html,<script>alert(1)</script>">unsafe</a>',
    '<p>安全正文</p><a href="//attacker.invalid/path">unsafe</a>',
    '<p>安全正文</p><a href="/relative">unsafe</a>',
    '<p>安全正文</p><a href="https://user:pass@example.test/">unsafe</a>',
    '<p>安全正文</p><a href="https://example.test/a b">unsafe</a>',
    '<p>安全正文</p><a href="https://example.test/a&#10;b">unsafe</a>',
    '<p>安全正文</p><a href="https://example.test/a&#127;b">unsafe</a>',
    '<p>安全正文</p><a href="https:\\attacker.invalid">unsafe</a>',
    '<p>安全正文</p><a href="https://example.test" target="_blank" ping="https://attacker.invalid" download>safe</a>',
    '<p>安全正文</p><math><mtext><table><mglyph><style><!--</style><img title="--><img src=x onerror=alert(1)>">',
]


@pytest.mark.parametrize('payload', ATTACKS)
def test_malicious_html_is_safe_in_storage_and_every_read_boundary(admin_client, member_client, payload):
    response = create(admin_client, payload)
    assert response.status_code == 201
    row = Announcement.objects.get(pk=response.json()['data']['id'])
    safe(row.content)
    assert 'discard-' not in row.content
    for path in (MANAGE, f'{MANAGE}{row.pk}/'):
        data = admin_client.get(path).json()['data']
        safe(data['items'][0]['content'] if 'items' in data else data['content'])
    assert admin_client.post(f'{MANAGE}{row.pk}/publish/', {'version': row.version}, format='json').status_code == 200
    data = member_client.get(f'{PUBLIC}{row.pk}/').json()['data']
    assert data['content_format'] == 'html'
    safe(data['content'])
    audit = str(list(OperationLog.objects.filter(resource='announcement', resource_id=str(row.pk)).values('description')))
    assert payload not in audit and 'attacker.invalid' not in audit


@pytest.mark.parametrize('payload', ['<p><br></p>', '<p>&nbsp; \n&#160;</p>', '<script>only script</script>',
    '<svg><text>only svg</text></svg>', '<style>only style</style>', '<p>\u200b\ufeff</p>'])
def test_semantically_empty_html_is_rejected_without_storage_or_audit(admin_client, payload):
    before = OperationLog.objects.count()
    assert create(admin_client, payload).status_code == 400
    assert not Announcement.objects.exists() and OperationLog.objects.count() == before


def test_safe_formatting_links_and_escaped_text_are_preserved(admin_client):
    payload = '<h2>标题</h2><p><strong>加粗</strong><em>斜体</em><u>下划线</u><s>删除</s><br>&lt;script&gt;字面量</p><h3>次标题</h3><ul><li>一</li></ul><ol><li>二</li></ol><blockquote>引用</blockquote><pre><code>a &lt; b</code></pre><hr><a href="https://example.test/path?q=1&amp;x=2">链接</a>'
    response = create(admin_client, payload)
    assert response.status_code == 201
    content = response.json()['data']['content']
    safe(content)
    for tag in ALLOWED:
        assert '<' + tag in content
    assert '&lt;script&gt;' in content and 'a &lt; b' in content


def test_raw_and_expanded_sanitized_length_are_both_bounded(admin_client):
    assert create(admin_client, '<script>' + 'x' * 20000 + '</script><p>x</p>').status_code == 400
    # rel扩展会使短于上限的源HTML超过20k；拒绝截断造成的语义破坏。
    source = '<a href="https://example.test">x</a>' * 450
    assert len(source) < 20000
    assert create(admin_client, source).status_code == 400
    response = create(admin_client, '<p>' + 'x' * 19993 + '</p>')
    assert response.status_code == 201 and len(response.json()['data']['content']) == 20000


def test_missing_format_is_literal_plain_and_unknown_format_is_rejected(admin_client, member_client):
    literal = '<script>legacy literal</script><strong>not markup</strong>'
    response = admin_client.post(MANAGE, {'title': 'legacy', 'content': literal, 'version': 0}, format='json')
    assert response.status_code == 201
    row = Announcement.objects.get(pk=response.json()['data']['id'])
    assert row.content_format == 'plain' and row.content == literal
    assert response.json()['data']['content_format'] == 'plain'
    assert create(admin_client, '<p>x</p>', content_format='markdown').status_code == 400
    assert admin_client.post(f'{MANAGE}{row.pk}/publish/', {'version': 1}, format='json').status_code == 200
    assert member_client.get(f'{PUBLIC}{row.pk}/').json()['data']['content'] == literal


def test_stored_unsanitized_html_is_defended_on_read_without_mutating_row(admin_client, member_client, admin_user):
    raw = '<p>历史正文</p><script>discard-stored-secret</script><img src="https://attacker.invalid/pixel"><a href="javascript:alert(1)">link</a>'
    row = Announcement.objects.create(title='historic unsafe', content=raw, content_format='html',
        status='published', published_at=timezone.now(), created_by=admin_user, updated_by=admin_user)
    for client, path in ((admin_client, MANAGE), (admin_client, f'{MANAGE}{row.pk}/'),
                         (member_client, PUBLIC), (member_client, f'{PUBLIC}{row.pk}/')):
        response = client.get(path)
        assert response.status_code == 200
        data = response.json()['data']
        content = data['items'][0]['content'] if 'items' in data else data['content']
        safe(content)
        assert 'discard-stored-secret' not in content and 'attacker.invalid' not in content
    row.refresh_from_db()
    assert row.content == raw  # 读取防御不能暗中修改内容/版本。


def test_html_edit_conflict_idempotency_and_revoked_replay_are_atomic(admin_client, admin_user):
    body = {'title': 'idempotent html', 'content': '<p onclick="x()">唯一正文</p>', 'content_format': 'html', 'version': 0}
    first = admin_client.post(MANAGE, body, format='json', HTTP_IDEMPOTENCY_KEY='richtext-create')
    replay = admin_client.post(MANAGE, body, format='json', HTTP_IDEMPOTENCY_KEY='richtext-create')
    assert first.status_code == replay.status_code == 201 and first.json() == replay.json()
    assert Announcement.objects.count() == 1
    changed = admin_client.post(MANAGE, {**body, 'content_format': 'plain'}, format='json', HTTP_IDEMPOTENCY_KEY='richtext-create')
    assert changed.status_code == 409
    row = Announcement.objects.get(pk=first.json()['data']['id'])
    response = admin_client.patch(f'{MANAGE}{row.pk}/', {**body, 'content': '<p>新版正文</p>', 'version': 1}, format='json')
    assert response.status_code == 200
    assert admin_client.patch(f'{MANAGE}{row.pk}/', {**body, 'version': 1}, format='json').status_code == 409
    row.refresh_from_db()
    assert row.content == '<p>新版正文</p>' and row.version == 2
    get_user_model().objects.filter(pk=admin_user.pk).update(is_staff=False, is_superuser=False)
    assert admin_client.post(MANAGE, body, format='json', HTTP_IDEMPOTENCY_KEY='richtext-create').status_code == 403


def test_richtext_unavailable_after_module_disable_or_session_revocation(admin_user, member_client):
    token = issue_session(admin_user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
    body = '<p>不能重放的正文</p>'
    assert create(member_client, body).status_code == 403
    with override_settings(ADMINCORE_MODULES=()):
        assert create(client, body).status_code == 404
    response = create(client, body)
    assert response.status_code == 201
    AuthSession.objects.filter(pk=token['sid']).update(revoked_at=timezone.now())
    assert create(client, body).status_code == 401
    assert Announcement.objects.count() == 1


def test_old_idempotency_response_is_sanitized_again_and_revoked_session_cannot_replay(admin_user):
    token = issue_session(admin_user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
    body = {'title': 'old replay', 'content': '<p>合法正文</p>', 'content_format': 'html', 'version': 0}
    first = client.post(MANAGE, body, format='json', HTTP_IDEMPOTENCY_KEY='old-richtext-policy')
    assert first.status_code == 201
    record = IdempotencyRecord.objects.get(actor=admin_user, key='old-richtext-policy')
    cached = record.response_data
    cached['data']['content'] = '<p>旧缓存正文</p><script>discard-old-cache</script><img src="https://attacker.invalid/pixel">'
    IdempotencyRecord.objects.filter(pk=record.pk).update(response_data=cached)
    before = OperationLog.objects.count()
    response = client.post(MANAGE, body, format='json', HTTP_IDEMPOTENCY_KEY='old-richtext-policy')
    assert response.status_code == 201 and response['Idempotency-Replayed'] == 'true'
    safe(response.json()['data']['content'])
    assert 'discard-old-cache' not in response.json()['data']['content']
    assert Announcement.objects.count() == 1 and OperationLog.objects.count() == before
    AuthSession.objects.filter(pk=token['sid']).update(revoked_at=timezone.now())
    response = client.post(MANAGE, body, format='json', HTTP_IDEMPOTENCY_KEY='old-richtext-policy')
    assert response.status_code == 401 and '旧缓存正文' not in str(response.json())
