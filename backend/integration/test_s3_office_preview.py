"""真实 MinIO + LibreOffice；仅由 validate_storage.py --office-image 显式调用。"""
from datetime import timedelta
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest
from django.utils import timezone
from pypdf import PdfReader

from apps.files import office_preview as service
from apps.files.models import FileModel, OfficePreview
from integration.test_s3_storage import s3_storage

pytest_plugins = ['tests.conftest']
pytestmark = pytest.mark.django_db


def load_script(name):
    path = Path(__file__).resolve().parents[2] / 'scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location('s3_office_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_s3_office_conversion_private_read_revocation_and_cleanup(s3_storage, admin_client,
        member_client, admin_user, settings, tmp_path):
    runner = load_script('office_preview_runner')
    fixture = load_script('office_preview_fixtures')
    image = os.environ['OFFICE_CONTRACT_IMAGE']
    assert runner.IMAGE.fullmatch(image)
    settings.ROOT_URLCONF = 'tests.office_urls'
    settings.ADMINCORE_MODULES = ('files', 'tasks')
    settings.ADMINCORE_BUILD_PROFILE = 'full'
    settings.ADMINCORE_OFFICE_PREVIEW_ENABLED = True
    settings.ADMINCORE_OFFICE_IMAGE = image
    content = fixture.odf_fixture('odt', 'ADMINCORES3REALOFFICE')
    upload = io.BytesIO(content)
    upload.name = 'private.odt'
    response = admin_client.post('/api/v1/files/', {'file': upload}, format='multipart')
    assert response.status_code == 201
    row = FileModel.objects.get(pk=response.json()['id'])
    with patch.object(type(s3_storage._wrapped), 'path', side_effect=AssertionError('S3 has no local path')):
        response = admin_client.post('/api/v1/files/' + str(row.pk) + '/office-preview/',
            {'lifecycle_version': row.lifecycle_version}, format='json', HTTP_IDEMPOTENCY_KEY='real-s3-office')
        assert response.status_code == 202
        identifier = response.json()['data']['id']
        claim = service.claim()
        assert claim['source'] == content and claim['source_sha256'] == hashlib.sha256(content).hexdigest()
        source = tmp_path / 'source.odt'
        source.write_bytes(claim['source'])
        source.chmod(0o644)
        try:
            actual_pdf = runner.convert(source, image)
        finally:
            source.unlink()
        service.finish(identifier, claim['token'], output=actual_pdf)
        response = admin_client.get('/api/v1/files/office-preview/jobs/' + identifier + '/pdf/')
        assert response.status_code == 200 and response['Content-Type'] == 'application/pdf'
        assert response['Cache-Control'] == 'private, no-store'
        reader = PdfReader(io.BytesIO(response.content), strict=True)
        assert 'ADMINCORES3REALOFFICE' in ''.join(''.join(page.extract_text() or '' for page in reader.pages).split())
        assert all('/Annots' not in page and '/AA' not in page for page in reader.pages)
        assert member_client.get('/api/v1/files/office-preview/jobs/' + identifier + '/pdf/').status_code == 404
        from rest_framework.test import APIClient
        assert APIClient().get('/api/v1/files/office-preview/jobs/' + identifier + '/pdf/').status_code == 401
        job = OfficePreview.objects.get(pk=identifier)
        key = job.output_key
        assert s3_storage.exists(key)
        for storage_key in (key, row.file.name):
            unsigned = s3_storage.url(storage_key).split('?')[0]
            with pytest.raises(urllib.error.HTTPError) as private:
                urllib.request.urlopen(unsigned)
            assert private.value.code == 403
        with row.file.open('rb') as stream:
            assert stream.read() == content
        # Same metadata/version but different S3 object bytes invalidates even completed output.
        with s3_storage.open(row.file.name, 'wb') as stream:
            stream.write(fixture.odf_fixture('ods', 'CHANGEDSOURCE'))
        assert admin_client.get('/api/v1/files/office-preview/jobs/' + identifier + '/pdf/').status_code == 403
        job.record.delete()
        OfficePreview.objects.filter(pk=identifier).update(expires_at=timezone.now() - timedelta(seconds=1))
        service.cleanup()
        assert not s3_storage.exists(key) and not OfficePreview.objects.filter(pk=identifier).exists()
        assert s3_storage.exists(row.file.name) and FileModel.objects.count() == 1
