"""可恢复分片上传：会话、分片校验、合并与过期清理。"""

import hashlib
import os
import re
import tempfile
from datetime import timedelta

from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.auth_app.write_authorization import authorize_write
from apps.core.data_scope import scope_queryset
from apps.core.exceptions import APIError

from .models import FileModel, ResumableUpload

MIN_CHUNK_SIZE = 256 * 1024
MAX_CHUNK_SIZE = 10 * 1024 * 1024
MAX_CHUNKS = 10_000
SESSION_TTL = timedelta(hours=24)
SHA256 = re.compile(r'^[0-9a-f]{64}$')


def _chunk_name(upload_id, index):
    return f'uploads/.chunks/{upload_id}/{index}.part'


def _visible(user):
    return scope_queryset(ResumableUpload.objects.all(), user, 'file', 'owner_id', fallback='self')


def get_session(user, upload_id, *, lock=False):
    queryset = _visible(user)
    if lock:
        queryset = queryset.select_for_update()
    row = queryset.filter(pk=upload_id).first()
    if row is None:
        raise NotFound('上传会话不存在或无权访问')
    if row.status == 'active' and row.expires_at <= timezone.now():
        row.status = 'expired'
        row.save(update_fields=['status', 'updated_at'])
        raise APIError('上传会话已过期', status_code=410)
    return row


def _int_value(value, label):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise APIError('上传参数必须为整数') from None
    return parsed


def start_session(request, *, name, total_size, chunk_size, content_type='', expected_sha256=''):
    actor = authorize_write(request, 'file:upload')
    name = os.path.basename(str(name or '')).strip()
    if not name or name in {'.', '..'} or len(name) > 255:
        raise APIError('文件名不合法')
    total_size = _int_value(total_size, '文件大小')
    chunk_size = _int_value(chunk_size, '分片大小')
    if total_size < 1 or total_size > getattr(settings, 'FILE_UPLOAD_MAX_SIZE', 50 * 1024 * 1024):
        raise APIError('文件大小超出限制', status_code=413)
    if not MIN_CHUNK_SIZE <= chunk_size <= MAX_CHUNK_SIZE:
        raise APIError('分片大小必须在 256 KiB 至 10 MiB 之间')
    total_chunks = (total_size + chunk_size - 1) // chunk_size
    if total_chunks > MAX_CHUNKS:
        raise APIError('分片数量超出限制')
    expected_sha256 = str(expected_sha256 or '').lower()
    if expected_sha256 and not SHA256.fullmatch(expected_sha256):
        raise APIError('文件 SHA-256 不合法')
    if not isinstance(content_type, str):
        raise APIError('MIME 类型不合法')
    return ResumableUpload.objects.create(
        owner=actor, original_name=name, content_type=content_type[:100], total_size=total_size,
        chunk_size=chunk_size, total_chunks=total_chunks, expected_sha256=expected_sha256,
        expires_at=timezone.now() + SESSION_TTL,
    )


def put_chunk(request, upload_id, index):
    index = _int_value(index, '分片序号')
    if index < 0:
        raise APIError('分片序号不合法')
    supplied = str(request.headers.get('X-Chunk-SHA256', '')).lower()
    if not SHA256.fullmatch(supplied):
        raise APIError('分片 SHA-256 不合法')
    try:
        content_length = int(request.META.get('CONTENT_LENGTH', '-1'))
    except ValueError:
        content_length = -1
    if content_length > MAX_CHUNK_SIZE:
        raise APIError('分片大小超出限制', status_code=413)
    body = request.body
    if len(body) > MAX_CHUNK_SIZE:
        raise APIError('分片大小超出限制', status_code=413)
    actual = hashlib.sha256(body).hexdigest()
    if actual != supplied:
        raise APIError('分片校验失败', status_code=422)
    with transaction.atomic():
        actor = authorize_write(request, 'file:upload')
        row = get_session(actor, upload_id, lock=True)
        if row.status != 'active':
            raise APIError('上传会话已完成或失效', status_code=409)
        if index >= row.total_chunks:
            raise APIError('分片序号超出范围')
        expected = row.chunk_size if index < row.total_chunks - 1 else row.total_size - row.chunk_size * (row.total_chunks - 1)
        if len(body) != expected:
            raise APIError('分片大小不符合会话约定')
        existing = (row.chunks or {}).get(str(index))
        if existing:
            if existing.get('sha256') != actual or existing.get('size') != len(body):
                raise APIError('同一分片序号已存在不同内容', status_code=409)
            # 同一分片的重试是幂等操作；不重复写对象存储。
            return row
        name = _chunk_name(row.pk, index)
        default_storage.save(name, ContentFile(body))
        chunks = dict(row.chunks or {})
        chunks[str(index)] = {'sha256': actual, 'size': len(body)}
        row.chunks = chunks
        row.save(update_fields=['chunks', 'updated_at'])
    return row


def complete_session(request, upload_id):
    with transaction.atomic():
        actor = authorize_write(request, 'file:upload')
        row = get_session(actor, upload_id, lock=True)
        if row.status == 'completed' and row.file_id:
            return row.file
        if row.status != 'active':
            raise APIError('上传会话已失效', status_code=409)
        chunks = row.chunks or {}
        if len(chunks) != row.total_chunks or any(str(i) not in chunks for i in range(row.total_chunks)):
            raise APIError('仍有分片未上传')
        temporary = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b')
        digest = hashlib.sha256()
        try:
            for index in range(row.total_chunks):
                name = _chunk_name(row.pk, index)
                with default_storage.open(name, 'rb') as source:
                    while True:
                        part = source.read(1024 * 1024)
                        if not part:
                            break
                        digest.update(part)
                        temporary.write(part)
            actual = digest.hexdigest()
            if row.expected_sha256 and actual != row.expected_sha256:
                raise APIError('文件校验失败', status_code=422)
            temporary.seek(0)
            uploaded = File(temporary, name=row.original_name)
            file_obj = FileModel(
                original_name=row.original_name,
                file=uploaded,
                file_type=os.path.splitext(row.original_name)[1].lower().lstrip('.')[:20],
                size=row.total_size,
                content_type=row.content_type,
                md5=hashlib.md5(temporary.read()).hexdigest(),
                uploader=actor,
            )
            temporary.seek(0)
            file_obj.save()
            row.status = 'completed'
            row.file = file_obj
            row.save(update_fields=['status', 'file', 'updated_at'])
        finally:
            temporary.close()
    for index in range(row.total_chunks):
        try:
            default_storage.delete(_chunk_name(row.pk, index))
        except Exception:
            pass
    return file_obj


def cleanup_expired_sessions(*, now=None, limit=100):
    now = now or timezone.now()
    cleaned = 0
    for row in ResumableUpload.objects.filter(status='active', expires_at__lte=now).order_by('expires_at')[:limit]:
        with transaction.atomic():
            locked = ResumableUpload.objects.select_for_update().filter(pk=row.pk, status='active', expires_at__lte=now).first()
            if locked is None:
                continue
            for index in range(locked.total_chunks):
                try:
                    default_storage.delete(_chunk_name(locked.pk, index))
                except Exception:
                    pass
            locked.status = 'expired'
            locked.save(update_fields=['status', 'updated_at'])
            cleaned += 1
    return cleaned
