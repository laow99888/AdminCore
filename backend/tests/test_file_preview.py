"""预览的鉴权、真实解析、安全边界与存储契约。"""
import io
from unittest.mock import patch

import pytest
from django.test import override_settings
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject
from rest_framework.test import APIClient

from tests.file_permissions import grant_files
from apps.files.models import FileModel
from apps.logs.models import OperationLog


def image_bytes(format='PNG'):
    output = io.BytesIO()
    image = Image.new('RGB', (24, 16), 'blue')
    if format == 'PNG':
        meta = PngInfo()
        meta.add_text('private-note', 'must-be-removed')
        image.save(output, format=format, pnginfo=meta)
    else:
        image.save(output, format=format)
    return output.getvalue()


def pdf_bytes(*, script=False, encrypted=False, pages=2, action=None):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=300)
    if script:
        writer.root_object[NameObject('/OpenAction')] = DictionaryObject({
            NameObject('/S'): NameObject('/JavaScript'), NameObject('/JS'): TextStringObject('app.alert("never execute")')})
    if encrypted:
        writer.encrypt('fixture-password')
    if action:
        writer.root_object[NameObject('/OpenAction')] = DictionaryObject({
            NameObject('/S'): NameObject(action), NameObject('/URI'): TextStringObject('https://example.invalid/')})
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def upload(client, name='image.png', content=None):
    stream = io.BytesIO(image_bytes() if content is None else content)
    stream.name = name
    result = client.post('/api/v1/files/', {'file': stream}, format='multipart')
    assert result.status_code == 201
    return result.json()['id']


def preview(client, id):
    return client.get(f'/api/v1/files/{id}/preview/')


def test_preview_auth_scope_deleted_and_restore(admin_client, member_client, member_user):
    grant_files(member_user, 'file:upload', 'file:download')
    id = upload(member_client)
    assert preview(APIClient(), id).status_code == 401
    assert preview(member_client, id).status_code == 200
    other = upload(admin_client)
    assert preview(member_client, other).status_code == 404
    assert member_client.delete(f'/api/v1/files/{id}/').status_code == 204
    assert preview(admin_client, id).status_code == 404
    assert admin_client.post(f'/api/v1/files/{id}/restore/', {'lifecycle_version': 2}, format='json').status_code == 200
    assert preview(member_client, id).status_code == 200


@pytest.mark.parametrize('extension,format', [('png', 'PNG'), ('jpg', 'JPEG'), ('jpeg', 'JPEG'), ('gif', 'GIF'), ('webp', 'WEBP'), ('bmp', 'BMP'), ('ico', 'ICO')])
def test_images_reencoded_to_png(admin_client, extension, format):
    content = image_bytes(format)
    with Image.open(io.BytesIO(content)) as original:
        expected_size = original.size
    result = preview(admin_client, upload(admin_client, f'image.{extension}', content))
    assert result.status_code == 200
    assert result['Content-Type'] == 'image/png'
    with Image.open(io.BytesIO(result.content)) as image:
        assert image.format == 'PNG' and image.size == expected_size
        assert 'private-note' not in image.info
    assert result['Cache-Control'] == 'private, no-store'
    assert result['X-Content-Type-Options'] == 'nosniff'
    assert result['X-Frame-Options'] == 'DENY'
    assert "sandbox" in result['Content-Security-Policy']
    assert int(result['Content-Length']) == len(result.content)
    assert FileModel.objects.get(pk=result.resolver_match.kwargs['pk']).download_count == 0
    assert OperationLog.objects.filter(action='read', resource='file').exists()


def test_pdf_real_content_and_headers(admin_client):
    content = pdf_bytes()
    result = preview(admin_client, upload(admin_client, 'example.pdf', content))
    assert result.status_code == 200 and result.content == content
    assert result['Content-Type'] == 'application/pdf'
    assert result['Content-Disposition'] == 'inline; filename="preview.pdf"'


@pytest.mark.parametrize('name,content,expected', [
    ('image.png', b'<script>alert(1)</script>', 422), ('image.jpg', image_bytes(), 422),
    ('script.svg', b'<svg onload="alert(1)"/>', 415), ('notes.txt', b'normal text', 415),
    ('bad.pdf', b'%PDF-1.7\ninvalid\n%%EOF', 422), ('truncated.pdf', pdf_bytes()[:-8], 422),
    ('encrypted.pdf', pdf_bytes(encrypted=True), 415), ('script.pdf', pdf_bytes(script=True), 415),
    ('action.pdf', pdf_bytes(action='/URI'), 415),
])
def test_invalid_and_active_content_rejected(admin_client, name, content, expected):
    result = preview(admin_client, upload(admin_client, name, content))
    assert result.status_code == expected
    assert result.json()['code'] == expected
    assert b'<script>' not in result.content


@override_settings(FILE_PREVIEW_MAX_PIXELS=100)
def test_image_pixel_limit(admin_client):
    assert preview(admin_client, upload(admin_client)).status_code == 413


@override_settings(FILE_PREVIEW_MAX_PDF_PAGES=1)
def test_pdf_page_limit(admin_client):
    assert preview(admin_client, upload(admin_client, 'pages.pdf', pdf_bytes())).status_code == 413


@override_settings(FILE_PREVIEW_MAX_SIZE=100)
def test_size_checked_against_actual_storage_not_only_database(admin_client):
    id = upload(admin_client, 'oversized.png', b'x' * 101)
    assert preview(admin_client, id).status_code == 413
    FileModel.objects.filter(pk=id).update(size=1)
    assert preview(admin_client, id).status_code == 413


def test_missing_and_unavailable_storage_sanitized(admin_client):
    id = upload(admin_client)
    record = FileModel.objects.get(pk=id)
    with patch.object(record.file.storage, 'open', side_effect=OSError('private-credential')):
        result = preview(admin_client, id)
        assert result.status_code == 503 and b'private-credential' not in result.content
    record.file.delete(save=False)
    assert preview(admin_client, id).status_code == 404


def test_animated_first_frame_and_trailing_payload_removed(admin_client):
    output = io.BytesIO()
    Image.new('RGB', (4, 4), 'red').save(output, format='GIF', save_all=True,
        append_images=[Image.new('RGB', (4, 4), 'blue')], duration=100, loop=0)
    result = preview(admin_client, upload(admin_client, 'animated.gif', output.getvalue() + b'<script>hidden</script>'))
    assert result.status_code == 200 and b'hidden' not in result.content
    with Image.open(io.BytesIO(result.content)) as image:
        assert not getattr(image, 'is_animated', False)
        assert image.convert('RGB').getpixel((0, 0)) == (255, 0, 0)


def test_indirect_external_pdf_action_rejected(admin_client):
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=300)
    # 动作类型也可为间接对象，不能依赖 JS/OpenAction 等显式键才拒绝。
    page[NameObject('/FixtureAction')] = DictionaryObject({NameObject('/S'): writer._add_object(NameObject('/Launch'))})
    output = io.BytesIO()
    writer.write(output)
    assert preview(admin_client, upload(admin_client, 'indirect.pdf', output.getvalue())).status_code == 415


def test_pdf_embedded_attachment_rejected(admin_client):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    writer.add_attachment('private.txt', b'private attachment')
    output = io.BytesIO()
    writer.write(output)
    assert preview(admin_client, upload(admin_client, 'attachment.pdf', output.getvalue())).status_code == 415
