"""扫描协议、安全拒收、历史读取、权限及持久审计。"""
from dataclasses import replace
import hashlib
import io
import json
import logging
import time
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import override_settings
import pytest

from apps.files.antivirus import checked_copy, ScanRejected
from apps.files.models import FileModel
from apps.logs.models import OperationLog
from config.antivirus import AntivirusConfig, load_antivirus
from tests.clamd_fixture import clamd_fixture
from tests.test_files import make_file

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('environment', [
    {'ADMINCORE_ANTIVIRUS_ENABLED': 'maybe'}, {'ADMINCORE_CLAMAV_ADDRESS': 'example.com'},
    {'ADMINCORE_CLAMAV_ADDRESS': '8.8.8.8'}, {'ADMINCORE_CLAMAV_ADDRESS': '0.0.0.0'},
    {'ADMINCORE_CLAMAV_ADDRESS': '169.254.169.254'}, {'ADMINCORE_CLAMAV_TIMEOUT': '0'},
    {'ADMINCORE_CLAMAV_TIMEOUT': '61'}, {'ADMINCORE_CLAMAV_MAX_BYTES': '524288001'},
    {'ADMINCORE_CLAMAV_PORT': '65536'}, {'ADMINCORE_CLAMAV_SOCKET': '../clamd.sock'},
])
def test_invalid_deployment_config_rejected(environment):
    with pytest.raises(ImproperlyConfigured):
        load_antivirus(environment)


def test_compose_service_name_is_allowed():
    config = load_antivirus({'ADMINCORE_ANTIVIRUS_ENABLED': 'True', 'ADMINCORE_CLAMAV_ADDRESS': 'clamav'})
    assert config.address == 'clamav' and config.port == 3310


def test_disabled_does_not_connect_or_rewind(settings):
    settings.ADMINCORE_ANTIVIRUS = AntivirusConfig()
    source = io.BytesIO(b'fixture-infected')
    source.seek(4)
    with patch('apps.files.antivirus.connect', side_effect=AssertionError('unexpected connection')):
        assert checked_copy(source, stage='test') is source
        assert source.tell() == 4


def test_stream_chunking_snapshot_and_source_cursor(settings):
    content = b'abcd' * 40000
    with clamd_fixture() as (config, scans):
        settings.ADMINCORE_ANTIVIRUS = config
        source = io.BytesIO(content)
        source.seek(17)
        with checked_copy(source, stage='test') as scanned:
            source.seek(0)
            source.write(b'changed')
            assert scanned.read() == content
        assert scans == [content]


@pytest.mark.parametrize('answer', [b'stream: ERROR\0', b'OK\0', b'stream: OK\n', b'x' * 4097 + b'\0', b''])
def test_invalid_reply_fails_closed(settings, answer):
    with clamd_fixture(response=answer) as (config, _):
        settings.ADMINCORE_ANTIVIRUS = config
        with pytest.raises(ScanRejected) as error:
            checked_copy(io.BytesIO(b'fixture'), stage='test')
        assert error.value.status_code == 503


def test_total_timeout_and_size_limit(settings):
    with clamd_fixture(delay=1.5, timeout=1) as (config, _):
        settings.ADMINCORE_ANTIVIRUS = config
        start = time.monotonic()
        with pytest.raises(ScanRejected) as error:
            checked_copy(io.BytesIO(b'fixture'), stage='test')
        assert error.value.status_code == 503 and time.monotonic() - start < 1.4
    with clamd_fixture(max_bytes=4) as (config, _):
        settings.ADMINCORE_ANTIVIRUS = config
        with pytest.raises(ScanRejected) as error:
            checked_copy(io.BytesIO(b'12345'), stage='test')
        assert error.value.status_code == 413


def test_upload_read_reopen_and_audit(admin_client, settings):
    with clamd_fixture() as (config, scans):
        settings.ADMINCORE_ANTIVIRUS = config
        response = admin_client.post('/api/v1/files/', {'file': make_file(content=b'clean')}, format='multipart')
        assert response.status_code == 201, response.content
        row = FileModel.objects.get(pk=response.json()['id'])
        with row.file.open('rb') as file:
            assert file.read() == b'clean'
        with row.file.open('rb') as file:
            assert file.read() == b'clean'
        response = admin_client.get(f'/api/v1/files/{row.pk}/download/')
        assert response.status_code == 200 and b''.join(response.streaming_content) == b'clean'
        response.close()
        assert scans == [b'clean'] * 4
        audit = OperationLog.objects.filter(resource='file_scan', after_values__stage='upload').get()
        assert audit.after_values['sha256'] == hashlib.sha256(b'clean').hexdigest()
        assert audit.after_values['engine'] == 'ClamAV 1.5.4'


def test_infected_upload_never_saved_and_audit_survives_rollback(admin_client, settings):
    with clamd_fixture() as (config, _), patch('apps.files.fields.FieldFile.save') as save:
        settings.ADMINCORE_ANTIVIRUS = config
        response = admin_client.post('/api/v1/files/', {'file': make_file(content=b'fixture-infected')}, format='multipart')
        assert response.status_code == 422, response.content
        save.assert_not_called()
        assert not FileModel.objects.exists()
        audit = OperationLog.objects.get(resource='file_scan')
        assert audit.after_values['outcome'] == 'infected' and audit.request_id
        assert 'Fixture-Test' not in json.dumps(audit.after_values)


def test_existing_infected_file_not_released_and_unprivileged_does_not_scan(admin_client, member_client, settings):
    response = admin_client.post('/api/v1/files/', {'file': make_file(content=b'fixture-infected')}, format='multipart')
    row = FileModel.objects.get(pk=response.json()['id'])
    with clamd_fixture() as (config, scans):
        settings.ADMINCORE_ANTIVIRUS = config
        assert member_client.get(f'/api/v1/files/{row.pk}/download/').status_code == 403
        assert not scans
        response = admin_client.get(f'/api/v1/files/{row.pk}/download/')
        assert response.status_code == 422
        assert FileModel.objects.filter(pk=row.pk).exists()
        assert row.file.storage.exists(row.file.name)
        row.refresh_from_db()
        assert row.download_count == 0
        assert OperationLog.objects.filter(resource='file_scan', after_values__outcome='infected').exists()


def test_import_and_avatar_inputs_blocked(admin_client, member_client, settings):
    from tests.test_personal_profile import AVATAR
    with clamd_fixture() as (config, scans):
        settings.ADMINCORE_ANTIVIRUS = config
        imported = admin_client.post('/api/v1/data-io/import/', {'resource': 'users',
                                    'file': make_file('source.csv', b'fixture-infected')}, format='multipart')
        assert imported.status_code == 422
        avatar = member_client.post(AVATAR, {'profile_version': 1,
                                   'file': make_file('picture.png', b'fixture-infected')}, format='multipart')
        assert avatar.status_code == 422
        assert len(scans) == 2 and not FileModel.objects.exists()


def test_offline_daemon_and_audit_failure_do_not_release(admin_client, settings):
    with clamd_fixture() as (config, _):
        pass
    settings.ADMINCORE_ANTIVIRUS = config
    response = admin_client.post('/api/v1/files/', {'file': make_file()}, format='multipart')
    assert response.status_code == 503 and not FileModel.objects.exists()
    with clamd_fixture() as (config, _), patch('apps.logs.audit.write_audit', side_effect=RuntimeError('private-data')):
        settings.ADMINCORE_ANTIVIRUS = config
        response = admin_client.post('/api/v1/files/', {'file': make_file()}, format='multipart')
        assert response.status_code == 503 and 'private-data' not in response.content.decode()
        assert not FileModel.objects.exists()


def test_filefield_save_cannot_bypass_scan(admin_user, settings):
    row = FileModel(original_name='fixture.txt', uploader=admin_user)
    with clamd_fixture() as (config, _):
        settings.ADMINCORE_ANTIVIRUS = config
        with pytest.raises(ScanRejected):
            row.file.save('fixture.txt', ContentFile(b'fixture-infected'), save=False)
    assert not row.file.name and not FileModel.objects.exists()


def test_runtime_log_does_not_disclose_content_or_signature():
    from apps.core.runtime_logging import SafeJSONFormatter
    record = logging.LogRecord('scan', logging.INFO, 'scan.py', 1, 'secret-content', (), None)
    record.event, record.scan_state = 'file.scan', 'infected'
    record.scan_sha256, record.scan_bytes = 'a' * 64, 68
    output = SafeJSONFormatter().format(record)
    assert 'secret-content' not in output
    assert json.loads(output)['scan_state'] == 'infected'
