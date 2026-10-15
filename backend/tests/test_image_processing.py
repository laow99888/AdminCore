"""真实 Pillow 编码、私有文件 API、权限与审计事务边界。"""
import hashlib
import io
from unittest.mock import patch

import pytest
from django.test import override_settings
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from rest_framework.test import APIClient

from apps.files.image_processing import BoundedOutput, MAX_BYTES
from tests.file_permissions import grant_files
from apps.files.models import FileModel
from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole


@pytest.fixture(autouse=True)
def enabled():
    with override_settings(ADMINCORE_IMAGE_PROCESSING_ENABLED=True):
        yield


def picture(size=(240, 160), format='PNG', color='blue', metadata=False):
    output = io.BytesIO()
    with Image.new('RGBA', size, color) as image:
        if format in {'JPEG', 'BMP'}:
            image = image.convert('RGB')
        options = {}
        if metadata and format == 'PNG':
            info = PngInfo()
            info.add_text('private-note', 'never-disclose-this')
            options['pnginfo'] = info
        image.save(output, format=format, **options)
    return output.getvalue()


def stream(content, name='fixture.png'):
    value = io.BytesIO(content)
    value.name = name
    return value


def upload(client, content=None, name='fixture.png'):
    response = client.post('/api/v1/files/', {'file': stream(content or picture(), name)}, format='multipart')
    assert response.status_code == 201
    return FileModel.objects.get(pk=response.json()['id'])


def process(client, row, **options):
    return client.post(f'/api/v1/files/{row.pk}/transform/',
                       {'lifecycle_version': row.lifecycle_version, **options}, format='multipart')


def grant(user, *codes):
    role = Role.objects.create(name='Image processor')
    UserRole.objects.create(user=user, role=role)
    for code in codes:
        resource, action = code.split(':')
        permission, _ = Permission.objects.get_or_create(code=code, defaults={
            'name': code, 'resource': resource, 'action': action})
        RolePermission.objects.create(role=role, permission=permission)


def test_default_off_keeps_original_download(admin_client):
    row = upload(admin_client)
    with override_settings(ADMINCORE_IMAGE_PROCESSING_ENABLED=False):
        config = admin_client.get('/api/v1/files/processing_config/')
        assert config.status_code == 200 and config.json()['data']['enabled'] is False
        assert config['Cache-Control'] == 'private, no-store'
        assert process(admin_client, row).status_code == 404
        assert admin_client.get(f'/api/v1/files/{row.pk}/preview/').status_code == 200
        response = admin_client.get(f'/api/v1/files/{row.pk}/download/')
        assert response.status_code == 200
        response.close()
    assert not OperationLog.objects.filter(resource='file_transform').exists()


@pytest.mark.parametrize('codes', [(), ('file:process',), ('file:download',)])
def test_requires_both_permissions(member_client, member_user, codes):
    grant_files(member_user, 'file:upload')
    row = upload(member_client)
    if codes:
        grant(member_user, *codes)
    assert process(member_client, row).status_code == 403


def test_auth_scope_deleted_and_private_purpose(admin_client, member_client, member_user):
    grant_files(member_user, 'file:upload')
    own = upload(member_client)
    other = upload(admin_client)
    grant(member_user, 'file:process', 'file:download')
    assert process(APIClient(), own).status_code == 401
    assert process(member_client, other).status_code == 404
    assert process(member_client, own).status_code == 200
    for purpose in ('avatar', 'import'):
        FileModel.objects.filter(pk=own.pk).update(purpose=purpose)
        assert process(admin_client, own).status_code == 404
    FileModel.objects.filter(pk=own.pk).update(purpose='general', is_deleted=True)
    assert process(admin_client, own).status_code == 404


@pytest.mark.parametrize('format,mime', [('png', 'image/png'), ('jpeg', 'image/jpeg'), ('webp', 'image/webp')])
def test_resize_format_metadata_headers_original_and_audit(admin_client, format, mime):
    original = picture(metadata=True)
    row = upload(admin_client, original)
    result = process(admin_client, row, width=100, height=100, format=format, quality=65)
    assert result.status_code == 200 and result['Content-Type'] == mime
    assert result['Cache-Control'] == 'private, no-store'
    assert result['X-Content-Type-Options'] == 'nosniff'
    assert result['X-Frame-Options'] == 'DENY'
    assert result['Content-Disposition'] == f'attachment; filename="processed.{format}"'
    assert int(result['Content-Length']) == len(result.content)
    with Image.open(io.BytesIO(result.content)) as image:
        assert image.size == (100, 67)
        assert not image.getexif() and 'private-note' not in image.info
    row.refresh_from_db()
    with row.file.open('rb') as source:
        assert source.read() == original
    assert row.lifecycle_version == 1 and row.download_count == 0
    audit = OperationLog.objects.get(resource='file_transform')
    assert audit.audit_version == 1 and audit.after_values['width'] == 100
    assert audit.after_values['source_sha256'] == hashlib.sha256(original).hexdigest()
    assert audit.after_values['output_sha256'] == hashlib.sha256(result.content).hexdigest()
    assert audit.after_values['quality'] == (None if format == 'png' else 65)
    assert 'never-disclose-this' not in audit.description and row.original_name not in audit.description
    assert FileModel.objects.count() == 1


@pytest.mark.parametrize('extension,format', [('jpg', 'JPEG'), ('jpeg', 'JPEG'), ('gif', 'GIF'),
                                           ('bmp', 'BMP'), ('ico', 'ICO'), ('webp', 'WEBP')])
def test_supported_source_encoders_first_frame(admin_client, extension, format):
    result = process(admin_client, upload(admin_client, picture(format=format), f'fixture.{extension}'), format='png')
    assert result.status_code == 200
    with Image.open(io.BytesIO(result.content)) as image:
        assert image.n_frames == 1 and image.format == 'PNG'


def test_no_upscale_and_jpeg_white_background(admin_client):
    row = upload(admin_client, picture(size=(12, 8), color=(0, 0, 0, 0)))
    result = process(admin_client, row, width=4096, height=4096, format='jpeg')
    with Image.open(io.BytesIO(result.content)) as image:
        assert image.size == (12, 8) and image.getpixel((0, 0)) == (255, 255, 255)


def test_exif_orientation_removed(admin_client):
    out = io.BytesIO()
    with Image.new('RGB', (30, 20), 'red') as source:
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = 'private-description'
        source.save(out, 'JPEG', exif=exif)
    result = process(admin_client, upload(admin_client, out.getvalue(), 'rotated.jpg'), format='png')
    with Image.open(io.BytesIO(result.content)) as image:
        assert image.size == (20, 30) and not image.getexif()
    assert b'private-description' not in result.content


@pytest.mark.parametrize('position,pixel', [('center', (120, 80)), ('bottom-right', (223, 143))])
def test_image_watermark_opacity_digest_and_no_storage(admin_client, position, pixel):
    row = upload(admin_client)
    mark = picture((40, 40), color='red', metadata=True)
    result = process(admin_client, row, format='png', watermark=stream(mark), position=position, opacity=100)
    assert result.status_code == 200
    with Image.open(io.BytesIO(result.content)) as image:
        assert image.getpixel(pixel)[:3] == (255, 0, 0)
        assert image.getpixel((0, 0))[:3] == (0, 0, 255)
    audit = OperationLog.objects.get(resource='file_transform')
    assert audit.after_values['watermark_sha256'] == hashlib.sha256(mark).hexdigest()
    assert audit.after_values['position'] == position and audit.after_values['opacity'] == 100
    assert b'never-disclose-this' not in result.content and FileModel.objects.count() == 1


@pytest.mark.parametrize('options', [{'width': 0}, {'height': 4097}, {'quality': 96}, {'quality': 39},
                                     {'opacity': 0}, {'format': 'svg'}, {'position': 'remote'},
                                     {'unexpected': 'no'}, {'lifecycle_version': 0}])
def test_strict_bounded_options(admin_client, options):
    assert process(admin_client, upload(admin_client), **options).status_code == 400
    assert not OperationLog.objects.filter(resource='file_transform').exists()


def test_duplicate_form_values_rejected(admin_client):
    row = upload(admin_client)
    assert process(admin_client, row, width=[100, 200]).status_code == 400


@pytest.mark.parametrize('data', [[], [{'width': 100}], 'invalid'])
def test_non_object_parameters_rejected(admin_client, data):
    row = upload(admin_client)
    assert admin_client.post(f'/api/v1/files/{row.pk}/transform/', data, format='json').status_code == 400


@pytest.mark.parametrize('content,name,status', [(b'<svg/>', 'image.svg', 415),
    (b'not-an-image', 'image.png', 422), (picture(format='JPEG'), 'image.png', 422)])
def test_unsupported_corrupt_mismatched_source(admin_client, content, name, status):
    assert process(admin_client, upload(admin_client, content, name)).status_code == status


@pytest.mark.parametrize('mark,status', [(b'<svg/>', 422), (b'x' * (512 * 1024 + 1), 400),
                                      (picture((1025, 1)), 413)], ids=['invalid-svg', 'oversize-bytes', 'oversize-width'])
def test_watermark_limits_and_validation(admin_client, mark, status):
    assert process(admin_client, upload(admin_client), watermark=stream(mark)).status_code == status


def test_stale_version_and_missing_version(admin_client):
    row = upload(admin_client)
    assert process(admin_client, row, lifecycle_version=2).status_code == 409
    assert admin_client.post(f'/api/v1/files/{row.pk}/transform/', {}, format='json').status_code == 400


def test_bounded_input_uses_actual_stream_length(admin_client):
    row = upload(admin_client)
    with patch('apps.files.image_processing.MAX_BYTES', 20):
        FileModel.objects.filter(pk=row.pk).update(size=1)
        assert process(admin_client, row).status_code == 413
    with patch('apps.files.image_processing.MAX_PIXELS', 100):
        assert process(admin_client, row).status_code == 413


def test_output_write_is_bounded():
    output = BoundedOutput()
    output.seek(MAX_BYTES)
    with pytest.raises(Exception) as error:
        output.write(b'1')
    assert error.value.status_code == 413 and output.getvalue() == b''


def test_storage_error_sanitized_and_audit_failure_has_no_result(admin_client):
    row = upload(admin_client)
    with patch('django.db.models.fields.files.FieldFile.open', side_effect=OSError('private storage URL secret')):
        result = process(admin_client, row)
    assert result.status_code == 503 and b'secret' not in result.content
    with patch('apps.logs.audit.write_audit', side_effect=RuntimeError('unavailable audit')):
        result = process(admin_client, row)
        assert result.status_code == 500 and result['Content-Type'] == 'application/json'
        assert b'unavailable audit' not in result.content
    assert not OperationLog.objects.filter(resource='file_transform').exists()


def test_compression_quality_changes_real_encoding(admin_client):
    output = io.BytesIO()
    with Image.effect_noise((256, 256), 80).convert('RGB') as image:
        image.save(output, 'PNG')
    row = upload(admin_client, output.getvalue())
    low = process(admin_client, row, format='jpeg', quality=40)
    high = process(admin_client, row, format='jpeg', quality=95)
    assert low.status_code == high.status_code == 200 and len(low.content) < len(high.content)


@pytest.mark.parametrize('boundary,status', [('permission', 403), ('scope', 404)])
def test_authorization_rechecked_after_encoding(member_client, member_user, boundary, status):
    from apps.files.image_processing import transform_content
    from apps.core.models import DataScopeGrant
    grant_files(member_user, 'file:upload')
    row = upload(member_client)
    grant(member_user, 'file:process', 'file:download')
    role = Role.objects.get(name='Image processor')
    def encode(*args, **kwargs):
        result = transform_content(*args, **kwargs)
        if boundary == 'permission':
            RolePermission.objects.filter(role=role, permission__code='file:process').delete()
        else:
            DataScopeGrant.objects.create(role=role, resource='file', scope='custom')
        return result
    with patch('apps.files.image_processing.transform_content', side_effect=encode):
        assert process(member_client, row).status_code == status
    assert not OperationLog.objects.filter(resource='file_transform').exists()


def test_upgrade_registers_permission_without_expanding_existing_roles(admin_user, monkeypatch):
    from django.core.management import call_command
    from io import StringIO
    monkeypatch.setenv('DJANGO_ENV', 'testing')
    admin_user.set_password('Fixture#Secure92743ForTest')
    admin_user.save(update_fields=['password'])
    role = Role.objects.create(name='系统管理员')
    call_command('bootstrap_admincore', stdout=StringIO())
    permission = Permission.objects.get(code='file:process')
    assert not RolePermission.objects.filter(role=role, permission=permission).exists()
    RolePermission.objects.create(role=role, permission=permission)
    call_command('bootstrap_admincore', stdout=StringIO())
    assert RolePermission.objects.filter(role=role, permission=permission).count() == 1
