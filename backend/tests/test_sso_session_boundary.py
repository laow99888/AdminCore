"""SSO guard must apply to stored session IDs, including workers without a JWT."""
import io
import zipfile
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from pypdf import PdfWriter
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.auth_app.models import AuthSession
from apps.auth_app.sessions import active_sessions, issue_session
from apps.files import office_preview as office
from apps.files.models import FileModel, OfficePreview
from apps.sso.configuration import provider
from apps.sso.models import ExternalIdentity, SSOSession
from apps.tasks.models import MaintenanceRequest, TaskRecord
from apps.tasks.reliability import valid_execution

pytestmark = pytest.mark.django_db
CHANGES = ('module', 'missing_config', 'config', 'revoked', 'binding_version', 'identity_user')


@pytest.fixture
def bound(settings, admin_user):
    settings.ROOT_URLCONF = 'tests.office_urls'
    settings.ADMINCORE_MODULES = ('files', 'tasks', 'sso')
    settings.ADMINCORE_BUILD_PROFILE = 'full'
    settings.ADMINCORE_OFFICE_PREVIEW_ENABLED = True
    settings.ADMINCORE_OFFICE_IMAGE = 'admincore/office@sha256:' + 'a' * 64
    settings.SSO_ISSUER = 'https://idp.example'
    settings.SSO_AUTHORIZATION_ENDPOINT = 'https://idp.example/authorize'
    settings.SSO_TOKEN_ENDPOINT = 'https://idp.example/token'
    settings.SSO_JWKS_URI = 'https://idp.example/jwks'
    settings.SSO_REDIRECT_URI = 'https://admin.example/api/v1/sso/callback/'
    settings.SSO_FRONTEND_ORIGIN = 'https://admin.example'
    settings.SSO_CLIENT_ID = 'session-boundary-fixture'
    settings.SSO_CLIENT_SECRET = 'session-boundary-fixture-secret'
    settings.SSO_ENCRYPTION_KEY = Fernet.generate_key().decode()
    settings.SSO_SESSION_SECONDS = 3600
    local, enterprise = issue_session(admin_user), issue_session(admin_user)
    enterprise['sso'] = True
    identity = ExternalIdentity.objects.create(user=admin_user, issuer=provider().issuer, subject='fixture-employee')
    link = SSOSession.objects.create(session_id=enterprise['sid'], identity=identity,
        binding_version=identity.binding_version, config_digest=provider().fingerprint)
    return admin_user, local, enterprise, link


def invalidate(settings, change, link):
    if change == 'module':
        settings.ADMINCORE_MODULES = ('files', 'tasks')
    elif change == 'missing_config':
        settings.SSO_CLIENT_SECRET = ''
    elif change == 'config':
        settings.SSO_CLIENT_SECRET = 'rotated-fixture-secret'
    elif change == 'revoked':
        ExternalIdentity.objects.filter(pk=link.identity_id).update(revoked_at=timezone.now())
    elif change == 'binding_version':
        ExternalIdentity.objects.filter(pk=link.identity_id).update(binding_version=2)
    else:
        other = get_user_model().objects.create_user('other-identity-owner', password='fixture-only#26')
        ExternalIdentity.objects.filter(pk=link.identity_id).update(user=other)


def client(token):
    value = APIClient()
    value.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
    return value


def source(user):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as package:
        package.writestr('[Content_Types].xml', '<Types>wordprocessingml.document.main+xml</Types>')
        package.writestr('word/document.xml', '<root/>')
    content = stream.getvalue()
    return FileModel.objects.create(uploader=user, original_name='fixture.docx', file_type='docx',
        size=len(content), file=ContentFile(content, name='fixture.docx'))


def submit(user, token):
    item = source(user)
    response = client(token).post(f'/api/v1/files/{item.pk}/office-preview/',
        {'lifecycle_version': item.lifecycle_version}, format='json', HTTP_IDEMPOTENCY_KEY='sso-worker-boundary')
    assert response.status_code == 202
    return OfficePreview.objects.get(pk=response.data['data']['id'])


def pdf():
    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(stream)
    return stream.getvalue()


@pytest.mark.parametrize('change', CHANGES)
def test_active_query_excludes_invalid_sso_and_preserves_local(bound, settings, change, django_assert_num_queries):
    user, local, enterprise, link = bound
    with django_assert_num_queries(1):
        assert set(active_sessions().filter(user=user).values_list('pk', flat=True)) == {
            UUID(local['sid']), UUID(enterprise['sid'])}
    invalidate(settings, change, link)
    with django_assert_num_queries(1):
        assert list(active_sessions().filter(user=user).values_list('pk', flat=True)) == [UUID(local['sid'])]
    # Ordinary row locks must never inherit a nullable SSO LEFT JOIN on PostgreSQL.
    with transaction.atomic():
        query = active_sessions().select_for_update().filter(user=user)
        assert 'LEFT OUTER JOIN' not in str(query.query)
        assert [row.pk for row in query] == [UUID(local['sid'])]


def test_module_disabled_does_not_parse_provider_for_local_sessions(bound, settings, monkeypatch):
    _, local, _, _ = bound
    settings.ADMINCORE_MODULES = ('files', 'tasks')
    def unexpected_provider():
        raise AssertionError('Disabled SSO must not require provider configuration')
    monkeypatch.setattr('apps.sso.sessions.provider', unexpected_provider)
    assert active_sessions().filter(pk=local['sid']).exists()


@pytest.mark.parametrize('change', CHANGES)
def test_office_claim_rejects_invalid_sso_session(bound, settings, change):
    user, _, enterprise, link = bound
    job = submit(user, enterprise)
    invalidate(settings, change, link)
    assert office.claim() is None
    job.record.refresh_from_db()
    assert job.record.status == 'failed' and job.record.error == 'preview_revoked'
    job.refresh_from_db()
    assert not job.output_key and not job.claim_digest


@pytest.mark.parametrize('change', CHANGES)
def test_office_finish_rejects_invalid_sso_session(bound, settings, change):
    user, _, enterprise, link = bound
    job = submit(user, enterprise)
    claim = office.claim()
    assert claim and claim['job_id'] == str(job.pk)
    invalidate(settings, change, link)
    with pytest.raises(PermissionDenied):
        office.finish(job.pk, claim['token'], output=pdf())
    job.refresh_from_db()
    assert not job.output_key and job.record.status == 'running'


@pytest.mark.parametrize('change', CHANGES)
def test_background_execution_uses_same_session_guard(bound, settings, change):
    user, local, enterprise, link = bound
    execution = MaintenanceRequest.objects.create(record=TaskRecord.objects.create(creator=user, name='fixture'),
        key='fixture', session_version=user.session_version, session_id=enterprise['sid'])
    assert valid_execution(execution, user)
    invalidate(settings, change, link)
    assert not valid_execution(execution, user)
    execution.session_id = local['sid']
    assert valid_execution(execution, user)


@pytest.mark.parametrize('change', CHANGES)
def test_session_lists_hide_invalid_sso_but_local_login_stays_valid(bound, settings, change):
    user, local, enterprise, link = bound
    invalidate(settings, change, link)
    api = client(local)
    response = api.get('/api/v1/auth/sessions/')
    assert response.status_code == 200
    assert [row['id'] for row in response.data['data']['items']] == [local['sid']]
    response = api.get('/api/v1/auth/online-users/')
    assert response.status_code == 200
    assert [(row['id'], row['session_count']) for row in response.data['data']['items']] == [(str(user.pk), 1)]
    # Filtering effective sessions does not destroy historical session/audit rows.
    assert AuthSession.objects.filter(pk=enterprise['sid'], revoked_at__isnull=True).exists()
