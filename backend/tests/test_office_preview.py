import io
import json
import zipfile
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from pypdf import PdfWriter, PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject

from apps.core.exceptions import APIError
from apps.files.models import FileModel, OfficePreview
from apps.files import office_preview as service
from apps.logs.models import OperationLog

IMAGE = 'admincore/office@sha256:' + 'a' * 64


def package(extension='docx', extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        if extension in service.ODF_MIMES:
            archive.writestr('mimetype', service.ODF_MIMES[extension])
            archive.writestr('content.xml', '<root/>')
            archive.writestr('META-INF/manifest.xml', '<manifest/>')
        else:
            root = {'docx': 'word/document.xml', 'xlsx': 'xl/workbook.xml', 'pptx': 'ppt/presentation.xml'}[extension]
            mime = {'docx': 'wordprocessingml.document', 'xlsx': 'spreadsheetml.sheet', 'pptx': 'presentationml.presentation'}[extension]
            archive.writestr('[Content_Types].xml', '<Types>application/vnd.openxmlformats-officedocument.' + mime + '.main+xml</Types>')
            archive.writestr(root, '<root/>')
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return output.getvalue()


def pdf(link=False):
    output = io.BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    if link:
        page[NameObject('/Annots')] = ArrayObject([DictionaryObject({
            NameObject('/Type'): NameObject('/Annot'), NameObject('/Subtype'): NameObject('/Link'),
            NameObject('/A'): DictionaryObject({NameObject('/S'): NameObject('/URI'),
                NameObject('/URI'): TextStringObject('https://example.invalid/private')})})])
    writer.write(output)
    return output.getvalue()


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.ROOT_URLCONF = 'tests.office_urls'
    settings.ADMINCORE_OFFICE_PREVIEW_ENABLED = True
    settings.ADMINCORE_OFFICE_IMAGE = IMAGE
    settings.ADMINCORE_MODULES = ('files', 'tasks')


@pytest.fixture
def source(admin_user):
    data = package()
    return FileModel.objects.create(original_name='private fixture.docx', file=ContentFile(data, name='fixture.docx'),
        file_type='docx', size=len(data), uploader=admin_user)


def submit(client, source, key='office-fixture'):
    return client.post('/api/v1/files/' + str(source.pk) + '/office-preview/',
        {'lifecycle_version': source.lifecycle_version}, format='json', HTTP_IDEMPOTENCY_KEY=key)


@pytest.mark.parametrize('extension', service.FORMATS)
def test_supported_package_family(extension):
    service.validate_package(package(extension), extension)


@pytest.mark.parametrize('extra', [
    {'../escape.xml': '<root/>'}, {'/absolute.xml': '<root/>'}, {'word\\escaped.xml': '<root/>'},
    {'word/vbaProject.bin': b'macro'}, {'Scripts/python/exploit.py': b'x'},
    {'word/embeddings/payload.bin': b'embedded'}, {'macro.xml': '<Type>macroEnabled</Type>'},
    {'macro.xml': '<office:script/>'.encode('utf-16')}, {'encrypted.xml': '<encryption-data/>'},
    {'entities.xml': '<!DOCTYPE root [<!ENTITY secret SYSTEM "file:///etc/passwd">]><root>&secret;</root>'},
])
def test_unsafe_package_rejected(extra):
    content = package(extra=extra)
    for name in extra:
        if '\\' in name:
            # Windows ZipFile normalizes native separators when producing fixtures.
            content = content.replace(name.replace('\\', '/').encode(), name.encode())
    with pytest.raises(APIError):
        service.validate_package(content, 'docx')


def test_zip_ratio_count_and_extension_mismatch_rejected():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('bomb.xml', b'a' * 100000)
    with pytest.raises(APIError):
        service.validate_package(output.getvalue(), 'docx')
    with pytest.raises(APIError):
        service.validate_package(package('xlsx'), 'docx')
    with pytest.raises(APIError):
        service.validate_package(b'not zip', 'docx')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for index in range(2001):
            archive.writestr(str(index), b'')
    with pytest.raises(APIError):
        service.validate_package(output.getvalue(), 'docx')


def test_pdf_projection_removes_links_but_keeps_strict_preview_guard():
    from apps.files.preview import _pdf
    with pytest.raises(APIError):
        _pdf(pdf(link=True))
    result = service.safe_pdf(pdf(link=True))
    assert _pdf(result)[1] == 'application/pdf'
    reader = PdfReader(io.BytesIO(result), strict=True)
    assert len(reader.pages) == 1 and '/Annots' not in reader.pages[0]
    with pytest.raises(ValueError):
        service.safe_pdf(b'invalid')


def test_office_audit_fields_match_explicit_manifest():
    from apps.files.manifest import MODULE
    from apps.logs.audit import FIELDS
    expected = ('job_id', 'lifecycle_version', 'source_sha256', 'output_sha256', 'status', 'engine')
    assert dict(MODULE.audit_fields)['file_office_preview'] == expected
    assert FIELDS['file_office_preview'] == expected


@pytest.mark.django_db
def test_actual_jwt_submit_claim_finish_private_read_and_audit(admin_client, member_client, source):
    response = submit(admin_client, source)
    assert response.status_code == 202
    identifier = response.json()['data']['id']
    assert submit(admin_client, source).json()['data']['id'] == identifier
    assert OfficePreview.objects.count() == 1
    claim = service.claim()
    with source.file.open('rb') as stream:
        assert claim['source'] == stream.read()
    assert claim['engine'] == IMAGE
    assert 'token' not in str(admin_client.get('/api/v1/files/office-preview/jobs/' + identifier + '/').json())
    assert service.claim() is None
    service.finish(identifier, claim['token'], output=pdf(link=True))
    response = admin_client.get('/api/v1/files/office-preview/jobs/' + identifier + '/pdf/')
    assert response.status_code == 200 and response['Content-Type'] == 'application/pdf'
    assert response['Cache-Control'] == 'private, no-store' and response['X-Frame-Options'] == 'DENY'
    assert member_client.get('/api/v1/files/office-preview/jobs/' + identifier + '/pdf/').status_code == 404
    with pytest.raises(ValueError):
        service.finish(identifier, claim['token'], output=pdf())
    logs = OperationLog.objects.filter(resource='file_office_preview')
    assert logs.count() == 3 and all(row.audit_version == 1 for row in logs)
    assert 'private fixture' not in str(list(logs.values())) and claim['token'] not in str(list(logs.values()))


@pytest.mark.django_db
def test_default_off_scope_version_permissions_and_limit(admin_client, member_client, source, settings):
    settings.ADMINCORE_OFFICE_PREVIEW_ENABLED = False
    assert not admin_client.get('/api/v1/files/office-preview/config/').json()['data']['enabled']
    assert submit(admin_client, source).status_code == 404
    settings.ADMINCORE_OFFICE_PREVIEW_ENABLED = True
    assert submit(member_client, source).status_code == 403
    assert admin_client.post('/api/v1/files/' + str(source.pk) + '/office-preview/',
        {'lifecycle_version': 99}, format='json', HTTP_IDEMPOTENCY_KEY='stale').status_code == 404
    for index in range(3):
        assert submit(admin_client, source, 'key-' + str(index)).status_code == 202
    assert submit(admin_client, source, 'over-limit').status_code == 429


@pytest.mark.django_db
@pytest.mark.parametrize('change', ['actor', 'session', 'source', 'content', 'module', 'engine'])
def test_claim_rechecks_identity_version_hash_and_module(admin_client, admin_user, source, settings, change):
    submit(admin_client, source)
    job = OfficePreview.objects.get()
    if change == 'actor':
        admin_user.is_active = False
        admin_user.save(update_fields=['is_active'])
    elif change == 'session':
        job.session.revoked_at = timezone.now()
        job.session.save(update_fields=['revoked_at'])
    elif change == 'source':
        source.lifecycle_version += 1
        source.save(update_fields=['lifecycle_version'])
    elif change == 'content':
        with source.file.storage.open(source.file.name, 'wb') as stream:
            stream.write(package(extra={'changed.txt': 'changed'}))
    elif change == 'module':
        settings.ADMINCORE_MODULES = ('files',)
    else:
        settings.ADMINCORE_OFFICE_IMAGE = 'admincore/office@sha256:' + 'b' * 64
    assert service.claim() is None
    if change not in ('module',):
        job.record.refresh_from_db()
        assert job.record.status == 'failed'


@pytest.mark.django_db
def test_cancel_rejects_late_completion_and_bad_token(admin_client, source):
    identifier = submit(admin_client, source).json()['data']['id']
    claim = service.claim()
    with pytest.raises(ValueError):
        service.finish(identifier, 'wrong', output=pdf())
    assert admin_client.delete('/api/v1/files/office-preview/jobs/' + identifier + '/').json()['data']['status'] == 'cancelled'
    with pytest.raises(ValueError):
        service.finish(identifier, claim['token'], output=pdf())
    assert not OfficePreview.objects.get().output_key


@pytest.mark.django_db
def test_result_refuses_revocation_replacement_and_expiry(admin_client, source):
    identifier = submit(admin_client, source).json()['data']['id']
    claim = service.claim()
    service.finish(identifier, claim['token'], output=pdf())
    job = OfficePreview.objects.get()
    job.expires_at = timezone.now() - timedelta(seconds=1)
    job.save(update_fields=['expires_at'])
    assert admin_client.get('/api/v1/files/office-preview/jobs/' + identifier + '/pdf/').status_code == 410
    key = job.output_key
    assert default_storage.exists(key)
    service.cleanup()
    job.refresh_from_db()
    assert not job.output_key and not default_storage.exists(key)
    assert source.file.storage.exists(source.file.name)


@pytest.mark.django_db
def test_lease_expiry_never_requeues_unknown_conversion(admin_client, source):
    identifier = submit(admin_client, source).json()['data']['id']
    claim = service.claim()
    OfficePreview.objects.filter(pk=identifier).update(claimed_at=timezone.now() - timedelta(seconds=121))
    service.cleanup()
    assert service.claim() is None
    with pytest.raises(ValueError):
        service.finish(identifier, claim['token'], output=pdf())


@pytest.mark.django_db
def test_audit_failure_removes_only_own_output_and_rolls_back(admin_client, source):
    identifier = submit(admin_client, source).json()['data']['id']
    claim = service.claim()
    with patch('apps.files.office_preview.write_audit', side_effect=RuntimeError('fixture')):
        with pytest.raises(RuntimeError):
            service.finish(identifier, claim['token'], output=pdf())
    assert not default_storage.exists('office-preview/' + identifier + '/preview.pdf')
    assert source.file.storage.exists(source.file.name)
    job = OfficePreview.objects.get()
    assert job.record.status == 'running' and not job.output_key


@pytest.mark.django_db
def test_history_deletion_preserves_output_cleanup_registration(admin_client, source):
    identifier = submit(admin_client, source).json()['data']['id']
    claim = service.claim()
    service.finish(identifier, claim['token'], output=pdf())
    job = OfficePreview.objects.get()
    key = job.output_key
    job.record.delete()
    job.refresh_from_db()
    assert job.record_id is None and default_storage.exists(key)
    assert admin_client.get('/api/v1/files/office-preview/jobs/' + identifier + '/pdf/').status_code == 404
    OfficePreview.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    service.cleanup()
    assert not OfficePreview.objects.filter(pk=job.pk).exists() and not default_storage.exists(key)
    assert source.file.storage.exists(source.file.name)


@pytest.mark.django_db
@pytest.mark.parametrize('change', ['source', 'session', 'profile'])
def test_completed_output_is_not_readable_after_original_authorization_changes(admin_client, source, admin_user, settings, change):
    identifier = submit(admin_client, source).json()['data']['id']
    claim = service.claim()
    service.finish(identifier, claim['token'], output=pdf())
    if change == 'source':
        with source.file.storage.open(source.file.name, 'wb') as stream:
            stream.write(package(extra={'changed.txt': 'changed'}))
    elif change == 'session':
        job = OfficePreview.objects.get()
        job.session.revoked_at = timezone.now()
        job.session.save(update_fields=['revoked_at'])
    else:
        settings.ADMINCORE_BUILD_PROFILE = 'minimal'
    assert admin_client.get('/api/v1/files/office-preview/jobs/' + identifier + '/pdf/').status_code in (401, 403, 404)


@pytest.mark.django_db
def test_stream_storage_never_requires_local_path(admin_client, source):
    from django.core.files import File
    from django.core.files.storage import Storage
    class RemoteStorage(Storage):
        def __init__(self):
            self.objects = {}
        def _open(self, name, mode='rb'):
            return File(io.BytesIO(self.objects[name]), name=name)
        def _save(self, name, content):
            self.objects[name] = content.read()
            return name
        def exists(self, name):
            return name in self.objects
        def delete(self, name):
            del self.objects[name]
        def path(self, name):
            raise AssertionError('Remote storage has no local path')
    storage = RemoteStorage()
    source.file.storage = storage
    source.file.name = storage.save('stream-source.docx', ContentFile(package()))
    source.save(update_fields=['file'])
    field = FileModel._meta.get_field('file')
    with patch.object(field, 'storage', storage):
        identifier = submit(admin_client, source).json()['data']['id']
        claim = service.claim()
        with patch('apps.files.office_preview.default_storage', storage):
            service.finish(identifier, claim['token'], output=pdf())
            assert admin_client.get('/api/v1/files/office-preview/jobs/' + identifier + '/pdf/').status_code == 200
            job = OfficePreview.objects.get()
            key = job.output_key
            job.expires_at = timezone.now() - timedelta(seconds=1)
            job.save(update_fields=['expires_at'])
            service.cleanup()
            assert not storage.exists(key) and storage.exists(source.file.name)


@pytest.mark.django_db
def test_idempotency_replay_rechecks_device_inside_transaction(admin_client, source):
    from rest_framework.exceptions import AuthenticationFailed
    assert submit(admin_client, source).status_code == 202
    with patch('apps.auth_app.sessions.locked_request_session', side_effect=AuthenticationFailed('revoked')):
        response = submit(admin_client, source)
    assert response.status_code == 401
    assert OfficePreview.objects.count() == 1
