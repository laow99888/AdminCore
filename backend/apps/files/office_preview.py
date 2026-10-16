"""Office 转换协议。应用不执行命令；宿主只能领取不可变源字节和提交 PDF。"""
import hashlib
import hmac
import io
import re
import secrets
import zipfile
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.auth_app.sessions import active_sessions, locked_request_session
from apps.core.data_scope import scope_queryset
from apps.core.exceptions import APIError
from apps.core.modules import module_enabled
from apps.logs.audit import write_audit
from apps.tasks.models import TaskRecord
from .models import FileModel, OfficePreview

MAX_BYTES = 10 * 1024 * 1024
FORMATS = ('docx', 'xlsx', 'pptx', 'odt', 'ods', 'odp')
LEASE_SECONDS = 120
TTL_SECONDS = 900
FAILURES = {'conversion_failed', 'conversion_timeout', 'unsafe_pdf', 'runner_lost', 'preview_revoked'}
ENGINE = re.compile(r'[a-z0-9][a-z0-9./:_-]{0,180}@sha256:[a-f0-9]{64}')
ODF_MIMES = {'odt': 'application/vnd.oasis.opendocument.text',
             'ods': 'application/vnd.oasis.opendocument.spreadsheet',
             'odp': 'application/vnd.oasis.opendocument.presentation'}


def available():
    return (getattr(settings, 'ADMINCORE_OFFICE_PREVIEW_ENABLED', False)
            and getattr(settings, 'ADMINCORE_BUILD_PROFILE', 'full') == 'full'
            and module_enabled('files') and module_enabled('tasks')
            and bool(ENGINE.fullmatch(getattr(settings, 'ADMINCORE_OFFICE_IMAGE', ''))))


def require_available():
    if not available():
        raise NotFound()


def read_source(source):
    if source.size > MAX_BYTES:
        raise APIError('Office 预览源超过 10 MiB', status_code=413)
    try:
        with source.file.open('rb') as stream:
            content = stream.read(MAX_BYTES + 1)
    except Exception:
        raise APIError('文件暂时不可读取', status_code=503) from None
    if len(content) > MAX_BYTES:
        raise APIError('Office 预览源超过 10 MiB', status_code=413)
    return content


def validate_package(content, extension):
    """只接受无宏/嵌入对象/加密的 XML 容器；不解包到文件系统。"""
    if extension not in FORMATS or not 0 < len(content) <= MAX_BYTES:
        raise ValidationError('不支持的 Office 文件或大小')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > 2000:
                raise ValueError('entries')
            total, names = 0, set()
            for item in entries:
                name = item.orig_filename
                if (name != item.filename or name in names or '\\' in name or '\x00' in name or ':' in name
                        or name.startswith('/') or any(part in ('.', '..') for part in name.split('/'))
                        or (item.external_attr >> 16) & 0o170000 == 0o120000
                        or item.flag_bits & 1 or item.file_size > 20 * 1024 * 1024
                        or item.file_size > max(item.compress_size, 1) * 100):
                    raise ValueError('entry')
                names.add(name)
                total += item.file_size
                if total > 50 * 1024 * 1024:
                    raise ValueError('expanded')
                lowered = name.lower()
                if any(part in lowered for part in ('vbaproject', 'vbasignature', 'macros/', 'basic/', 'scripts/', 'embeddings/', 'oleobject', 'encryptedpackage', 'encryptioninfo')):
                    raise ValueError('active content')
                # Bounded read validates every CRC and detects macro/encryption metadata.
                data = archive.read(item)
                if lowered.endswith(('.xml', '.rels')) and any(marker in data.replace(b'\x00', b'').lower() for marker in (
                        b'macroenabled', b'vba', b'<script:', b'office:script', b'encryption-data',
                        b'event-listener', b'<!doctype', b'<!entity')):
                    raise ValueError('active xml')
            if extension in ODF_MIMES:
                if archive.read('mimetype').decode('ascii') != ODF_MIMES[extension]:
                    raise ValueError('mimetype')
                if 'content.xml' not in names or 'META-INF/manifest.xml' not in names:
                    raise ValueError('odf')
            else:
                root = {'docx': 'word/document.xml', 'xlsx': 'xl/workbook.xml', 'pptx': 'ppt/presentation.xml'}[extension]
                if '[Content_Types].xml' not in names or root not in names:
                    raise ValueError('ooxml')
                content_types = archive.read('[Content_Types].xml').lower()
                marker = {'docx': b'wordprocessingml.document.main+xml',
                          'xlsx': b'spreadsheetml.sheet.main+xml',
                          'pptx': b'presentationml.presentation.main+xml'}[extension]
                if marker not in content_types:
                    raise ValueError('type')
    except (ValueError, KeyError, UnicodeError, RuntimeError, NotImplementedError, zipfile.BadZipFile, OSError):
        raise APIError('Office 文件损坏、加密或包含不支持的活动内容', status_code=422) from None


def safe_pdf(content):
    """只保留页面绘制属性；丢弃注解/动作/表单，然后仍执行现有严格 PDF 检查。"""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
    from .preview import _pdf, FORBIDDEN_KEYS, FORBIDDEN_ACTIONS
    if not 0 < len(content) <= MAX_BYTES:
        raise ValueError('unsafe_pdf')
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted or not 0 < len(reader.pages) <= 100:
            raise ValueError('unsafe_pdf')
        writer = PdfWriter()
        allowed = {'/Type', '/Parent', '/Contents', '/Resources', '/MediaBox', '/CropBox', '/Rotate', '/UserUnit'}
        for page in reader.pages:
            for key in list(page):
                if key not in allowed:
                    del page[key]
            pending, seen, count = [(page, 0)], set(), 0
            while pending:
                obj, depth = pending.pop()
                count += 1
                if count > 20000 or depth > 100:
                    raise ValueError('unsafe_pdf')
                if isinstance(obj, IndirectObject):
                    marker = (obj.idnum, obj.generation)
                    if marker in seen:
                        continue
                    seen.add(marker)
                    obj = obj.get_object()
                if isinstance(obj, DictionaryObject):
                    if (FORBIDDEN_KEYS.intersection(obj) or obj.get('/S') in FORBIDDEN_ACTIONS
                            or obj.get('/Type') == '/EmbeddedFile'):
                        raise ValueError('unsafe_pdf')
                    pending.extend((value, depth + 1) for key, value in obj.items() if key != '/Parent')
                elif isinstance(obj, ArrayObject):
                    pending.extend((value, depth + 1) for value in obj)
            writer.add_page(page)
        writer.add_metadata({})
        output = io.BytesIO()
        writer.write(output)
        result = output.getvalue()
        if len(result) > MAX_BYTES:
            raise ValueError('unsafe_pdf')
        return _pdf(result)[0]
    except Exception:
        raise ValueError('unsafe_pdf') from None


def scoped_files(actor):
    return scope_queryset(FileModel.objects.filter(purpose='general', is_deleted=False), actor,
                          'file', 'uploader_id', fallback='self')


def authorized(job, *, content=False):
    from apps.permissions.permissions import has_permission_code
    actor = get_user_model().objects.select_for_update().filter(pk=job.actor_id, is_active=True).first()
    if (not available() or actor is None or actor.must_change_password
            or actor.session_version != job.session_version or not job.session_id
            or not active_sessions().select_for_update().filter(pk=job.session_id, user=actor).exists()
            or not has_permission_code(actor, 'file:download')
            or job.engine != getattr(settings, 'ADMINCORE_OFFICE_IMAGE', '')):
        raise PermissionDenied('预览身份或权限已失效')
    source = scoped_files(actor).select_for_update().filter(pk=job.source_id,
        lifecycle_version=job.source_version).first()
    if source is None:
        raise PermissionDenied('原文件或数据范围已变化')
    data = read_source(source) if content else None
    if content and not hmac.compare_digest(hashlib.sha256(data).hexdigest(), job.source_sha256):
        raise PermissionDenied('原文件内容已变化')
    return actor, source, data


@transaction.atomic
def submit(request, file_id, version):
    require_available()
    from apps.permissions.permissions import has_permission_code
    actor = get_user_model().objects.select_for_update().get(pk=request.user.pk)
    session = locked_request_session(request, actor)
    if actor.must_change_password or not has_permission_code(actor, 'file:download'):
        raise PermissionDenied()
    source = scoped_files(actor).select_for_update().filter(pk=file_id).first()
    if source is None:
        raise NotFound()
    if source.lifecycle_version != version:
        raise APIError('原文件已变化，请刷新后重试', status_code=409)
    # Bound active queue per actor even when clients deliberately vary idempotency keys.
    if OfficePreview.objects.filter(actor=actor, record__status__in=['pending', 'running'], expires_at__gt=timezone.now()).count() >= 3:
        raise APIError('等待转换的文件过多，请稍后重试', status_code=429)
    data = read_source(source)
    validate_package(data, source.file_type.lower())
    record = TaskRecord.objects.create(name='Office 文件安全预览', task_type='other', creator=actor,
        related_resource='file:office-preview')
    job = OfficePreview.objects.create(record=record, source=source, actor=actor, session=session,
        session_version=actor.session_version, source_version=version,
        source_sha256=hashlib.sha256(data).hexdigest(), engine=settings.ADMINCORE_OFFICE_IMAGE,
        expires_at=timezone.now() + timedelta(seconds=TTL_SECONDS))
    audit(job, actor, 'office_preview_requested', request=request)
    return job


def audit(job, actor, description, request=None):
    write_audit(resource='file_office_preview', identifier=job.source_id or '', actor=actor,
        request=request, record=job.record, description=description,
        after={'job_id': str(job.pk), 'lifecycle_version': job.source_version,
               'source_sha256': job.source_sha256, 'output_sha256': job.output_sha256,
               'status': job.record.status, 'engine': job.engine})


def cleanup():
    """只清理登记产物；先锁任务后锁预览，与任务历史删除保持同序。"""
    from django.db.models import Q
    now = timezone.now()
    expired = Q(expires_at__lte=now) & (~Q(output_key='') | Q(record__isnull=True)
        | Q(record__status__in=['pending', 'running']))
    lost = Q(record__status='running', claimed_at__lt=now - timedelta(seconds=LEASE_SECONDS))
    rows = OfficePreview.objects.filter(expired | lost).order_by('expires_at').values_list('pk', flat=True)[:100]
    for identifier in list(rows):
        with transaction.atomic():
            probe = OfficePreview.objects.filter(pk=identifier).values('record_id').first()
            if probe is None:
                continue
            record = TaskRecord.objects.select_for_update().filter(pk=probe['record_id']).first()
            job = OfficePreview.objects.select_for_update().filter(pk=identifier).first()
            if job is None:
                continue
            if job.expires_at <= now:
                expected = 'office-preview/' + str(job.pk) + '/preview.pdf'
                if job.output_key:
                    if job.output_key != expected:
                        raise ValueError('invalid_office_output_key')
                    default_storage.delete(job.output_key)
                    job.output_key = ''
                    job.save(update_fields=['output_key'])
                if job.record_id is None:
                    job.delete()
                elif record and record.status in ('pending', 'running'):
                    record.mark_failed('runner_lost')
            elif (record and record.status == 'running' and job.claimed_at is not None
                    and job.claimed_at < now - timedelta(seconds=LEASE_SECONDS)):
                record.mark_failed('runner_lost')


def claim():
    cleanup()
    if not available():
        return None
    for identifier in list(OfficePreview.objects.filter(record__status='pending', expires_at__gt=timezone.now()).order_by('created_at').values_list('pk', flat=True)[:100]):
        with transaction.atomic():
            # Every path locks actor before job/file, matching ordinary authenticated writes.
            probe = OfficePreview.objects.filter(pk=identifier).first()
            if probe is None or probe.record_id is None:
                continue
            try:
                actor, source, data = authorized(probe, content=True)
            except (PermissionDenied, APIError):
                record = TaskRecord.objects.select_for_update().filter(pk=probe.record_id).first()
                if record:
                    record.mark_failed('preview_revoked')
                continue
            record = TaskRecord.objects.select_for_update().filter(pk=probe.record_id).first()
            job = OfficePreview.objects.select_for_update().filter(pk=identifier).first()
            if job is None or job.record_id is None or record is None:
                continue
            job.record = record
            if job.record.status != 'pending' or job.claim_digest:
                continue
            try:
                validate_package(data, source.file_type.lower())
            except (ValidationError, APIError):
                job.record.mark_failed('preview_revoked')
                continue
            token = secrets.token_hex(32)
            job.claim_digest = hashlib.sha256(token.encode()).hexdigest()
            job.claimed_at = timezone.now()
            job.save(update_fields=['claim_digest', 'claimed_at'])
            job.record.mark_started()
            return {'job_id': str(job.pk), 'token': token, 'extension': source.file_type.lower(),
                    'source': data, 'engine': job.engine, 'source_sha256': job.source_sha256}
    return None


def finish(identifier, token, *, output=None, code=None):
    if code is not None and code not in FAILURES:
        raise ValueError('invalid_failure')
    content = safe_pdf(output) if code is None else None
    if content is not None:
        from .antivirus import checked_upload
        scanned = checked_upload(ContentFile(content, name='preview.pdf'), stage='office_output')
        try:
            content = scanned.read()
        finally:
            scanned.close()
    saved = None
    try:
        with transaction.atomic():
            probe = OfficePreview.objects.filter(pk=identifier).first()
            if probe is None:
                raise ValueError('claim_not_running')
            actor, source, data = authorized(probe, content=True)
            record = TaskRecord.objects.select_for_update().filter(pk=probe.record_id).first()
            job = OfficePreview.objects.select_for_update().filter(pk=identifier).first()
            if job is None or job.record_id is None or record is None:
                raise ValueError('claim_not_running')
            job.record = record
            if (not isinstance(token, str) or not hmac.compare_digest(job.claim_digest, hashlib.sha256(token.encode()).hexdigest())
                    or job.record.status != 'running' or job.expires_at <= timezone.now()
                    or job.claimed_at is None or job.claimed_at < timezone.now() - timedelta(seconds=LEASE_SECONDS)):
                raise ValueError('claim_not_running')
            if code:
                job.record.mark_failed(code)
            else:
                key = 'office-preview/' + str(job.pk) + '/preview.pdf'
                if default_storage.exists(key):
                    raise ValueError('output_already_exists')
                saved = default_storage.save(key, ContentFile(content))
                if saved != key:
                    raise ValueError('output_conflict')
                job.output_key, job.output_sha256 = key, hashlib.sha256(content).hexdigest()
                job.expires_at = timezone.now() + timedelta(seconds=TTL_SECONDS)
                job.save(update_fields=['output_key', 'output_sha256', 'expires_at'])
                job.record.mark_success({'preview_ready': True, 'expires_at': job.expires_at.isoformat()})
            audit(job, actor, 'office_preview_failed' if code else 'office_preview_completed')
    except Exception:
        if saved:
            default_storage.delete(saved)
        raise


@transaction.atomic
def get_job(request, identifier, *, cancel=False, pdf=False):
    require_available()
    probe = OfficePreview.objects.filter(pk=identifier, actor=request.user, record__isnull=False).first()
    if probe is None:
        raise NotFound()
    actor, source, data = authorized(probe, content=True)
    locked_request_session(request, actor)
    record = TaskRecord.objects.select_for_update().filter(pk=probe.record_id).first()
    job = OfficePreview.objects.select_for_update().filter(pk=identifier).first()
    if job is None or job.record_id is None or record is None:
        raise NotFound()
    job.record = record
    if job.expires_at <= timezone.now():
        raise APIError('Office 预览已过期，请重新生成', status_code=410)
    if cancel and job.record.status in ('pending', 'running'):
        job.record.mark_cancelled()
        audit(job, actor, 'office_preview_cancelled', request=request)
    if not pdf:
        return job
    if job.record.status != 'success' or job.output_key != 'office-preview/' + str(job.pk) + '/preview.pdf':
        raise APIError('Office 预览尚未完成', status_code=409)
    try:
        with default_storage.open(job.output_key, 'rb') as stream:
            content = stream.read(MAX_BYTES + 1)
    except Exception:
        raise APIError('预览暂时不可读取', status_code=503) from None
    if len(content) > MAX_BYTES or hashlib.sha256(content).hexdigest() != job.output_sha256:
        raise APIError('预览内容校验失败', status_code=422)
    from .antivirus import checked_upload
    scanned = checked_upload(ContentFile(content, name='preview.pdf'), stage='office_read')
    try:
        content = scanned.read()
    finally:
        scanned.close()
    from .preview import _pdf
    _pdf(content)
    audit(job, actor, 'office_preview_read', request=request)
    return content
