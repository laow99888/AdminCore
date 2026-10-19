"""可恢复分片上传：会话、分片校验、合并与过期清理。"""

import hashlib
import logging
import os
import re
import tempfile
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.auth_app.write_authorization import authorize_write
from apps.core.data_scope import scope_queryset
from apps.core.exceptions import APIError

from .models import FileModel, ResumableUpload
from .upload_validation import validate_upload_metadata

MIN_CHUNK_SIZE = 256 * 1024
MAX_CHUNK_SIZE = 10 * 1024 * 1024
MAX_CHUNKS = 10_000
SESSION_TTL = timedelta(hours=24)
SHA256 = re.compile(r'^[0-9a-f]{64}$')
logger = logging.getLogger(__name__)


def _chunk_name(upload_id, index):
    return f'uploads/.chunks/{upload_id}/{index}.part'


def _stored_chunk_name(upload_id, index, chunks):
    return chunks.get(str(index), {}).get('name') or _chunk_name(upload_id, index)


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
    validate_upload_metadata(name, total_size)
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
    saved = []
    try:
        return _put_chunk(request, upload_id, index, saved)
    except Exception:
        for name in saved:
            try:
                default_storage.delete(name)
            except Exception:
                # 会话过期清理也枚举此会话专属目录，重试未登记的暂存对象。
                logger.error('Failed to clean uncommitted upload chunk')
        raise


def _put_chunk(request, upload_id, index, saved):
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
        name = f'uploads/.chunks/{row.pk}/{index}_{uuid.uuid4().hex}.part'
        name = default_storage.save(name, ContentFile(body))
        saved.append(name)
        chunks = dict(row.chunks or {})
        chunks[str(index)] = {'sha256': actual, 'size': len(body), 'name': name}
        row.chunks = chunks
        row.save(update_fields=['chunks', 'updated_at'])
    return row


def complete_session(request, upload_id):
    with transaction.atomic():
        actor = authorize_write(request, 'file:upload')
        snapshot = get_session(actor, upload_id, lock=True)
        if snapshot.status == 'completed' and snapshot.file_id:
            return snapshot.file
        if snapshot.status != 'active':
            raise APIError('上传会话已失效', status_code=409)
        validate_upload_metadata(snapshot.original_name, snapshot.total_size)
        chunks = dict(snapshot.chunks or {})
        if len(chunks) != snapshot.total_chunks or any(str(i) not in chunks for i in range(snapshot.total_chunks)):
            raise APIError('仍有分片未上传')
    # 合并和校验不持有用户/会话行锁，最终提交前再次锁定并复核。
    file_obj = None
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b') as temporary:
        digest, md5 = hashlib.sha256(), hashlib.md5()
        total = 0
        try:
            for index in range(snapshot.total_chunks):
                part_digest, part_size = hashlib.sha256(), 0
                with default_storage.open(_stored_chunk_name(snapshot.pk, index, chunks), 'rb') as source:
                    while part := source.read(1024 * 1024):
                        total += len(part)
                        part_size += len(part)
                        if total > snapshot.total_size:
                            raise APIError('文件大小不符合会话约定', status_code=422)
                        part_digest.update(part); digest.update(part); md5.update(part)
                        temporary.write(part)
                if part_size != chunks[str(index)]['size'] or part_digest.hexdigest() != chunks[str(index)]['sha256']:
                    raise APIError('分片校验失败', status_code=422)
            if total != snapshot.total_size or (snapshot.expected_sha256 and digest.hexdigest() != snapshot.expected_sha256):
                raise APIError('文件校验失败', status_code=422)
        except Exception:
            # 另一完成请求可能已提交并删除分片；只在重新授权后复用其结果。
            with transaction.atomic():
                current_actor = authorize_write(request, 'file:upload')
                current = get_session(current_actor, upload_id, lock=True)
                if current.status == 'completed' and current.file_id:
                    return current.file
            raise
        committed = False
        try:
            temporary.seek(0)
            extension = validate_upload_metadata(snapshot.original_name, snapshot.total_size)
            file_obj = FileModel(original_name=snapshot.original_name, file_type=extension[:20], size=total,
                content_type=snapshot.content_type, md5=md5.hexdigest(), uploader=actor,
                created_at=timezone.now())
            # 扫描和对象上传均在行锁之外；提交失败只补偿本次生成的唯一存储键。
            file_obj.file.save(snapshot.original_name, File(temporary, name=snapshot.original_name), save=False)
            with transaction.atomic():
                actor = authorize_write(request, 'file:upload')
                row = get_session(actor, upload_id, lock=True)
                if row.status == 'completed' and row.file_id:
                    return row.file
                if row.status != 'active' or row.chunks != chunks:
                    raise APIError('上传会话已变化，请重新读取状态', status_code=409)
                validate_upload_metadata(row.original_name, row.total_size)
                file_obj.uploader = actor
                file_obj.save()
                row.status = 'completed'
                row.file = file_obj
                row.save(update_fields=['status', 'file', 'updated_at'])
            committed = True
        finally:
            if file_obj is not None and not committed:
                from .serializers import cleanup_failed_upload
                cleanup_failed_upload(file_obj)
    with transaction.atomic():
        current = ResumableUpload.objects.select_for_update().get(pk=snapshot.pk)
        _cleanup_chunks(current)
    return file_obj


def _cleanup_chunks(row):
    """只清理已有终态会话的专属目录；成功标记与失败重试均持久化。"""
    if row.chunks_cleaned:
        return True
    prefix = f'uploads/.chunks/{row.pk}/'
    names = {_stored_chunk_name(row.pk, index, row.chunks or {}) for index in range(row.total_chunks)}
    try:
        try:
            directories, files = default_storage.listdir(prefix)
        except FileNotFoundError:
            directories, files = [], []
        if directories or any('/' in name or '\\' in name or name in {'.', '..'} for name in files):
            raise ValueError('invalid_chunk_directory')
        names.update(prefix + name for name in files)
        if any(not name.startswith(prefix) or '/' in name[len(prefix):] or '\\' in name for name in names):
            raise ValueError('invalid_chunk_key')
        for name in names:
            default_storage.delete(name)
    except Exception:
        logger.error('Upload chunk cleanup deferred')
        return False
    row.chunks_cleaned = True
    row.save(update_fields=['chunks_cleaned', 'updated_at'])
    return True


def cleanup_expired_sessions(*, now=None, limit=100):
    now = now or timezone.now()
    cleaned = 0
    candidates = (Q(status='active', expires_at__lte=now) | Q(status__in=['completed', 'expired']))
    for row in ResumableUpload.objects.filter(candidates, chunks_cleaned=False).order_by('updated_at', 'pk')[:limit]:
        with transaction.atomic():
            locked = ResumableUpload.objects.select_for_update().filter(candidates, pk=row.pk, chunks_cleaned=False).first()
            if locked is None:
                continue
            if locked.status == 'active':
                locked.status = 'expired'
                locked.save(update_fields=['status', 'updated_at'])
            if _cleanup_chunks(locked):
                cleaned += 1
            else:
                # 多个失败会话公平轮换，避免单条存储故障饿死后续清理。
                locked.save(update_fields=['updated_at'])
    return cleaned
