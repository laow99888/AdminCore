"""导入提交和接续；源内容不变、单批次最多一个活动执行。"""
import hashlib

from django.db import transaction
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from apps.core.data_scope import scope_queryset
from apps.core.events import enqueue_event
from apps.core.modules import task_enabled
from apps.logs.audit import snapshot, write_audit
from apps.tasks.models import TaskRecord, ImportBatch, ImportExecution
from apps.tasks.reliability import authorize, policy


class ExecutionConflict(APIException):
    status_code = 409
    default_detail = '任务已开始、已完成或已被接续，请刷新状态'


def digest(source):
    from django.conf import settings
    sha = hashlib.sha256()
    total = 0
    with source.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            if total > min(settings.FILE_UPLOAD_MAX_SIZE, 10 * 1024 * 1024):
                raise ValidationError('导入源文件最多 10 MiB')
            sha.update(chunk)
    return sha.hexdigest()


def register(record, source, request=None, batch=None, attempt=1):
    current = policy('import')
    batch = batch or ImportBatch.objects.create(source=source, source_sha256=digest(source.file),
                                               resource=record.related_resource, active_record=record)
    session_id = request.auth.get('sid') if request is not None and request.auth is not None else None
    execution = ImportExecution.objects.create(record=record, batch=batch, attempt=attempt, policy=current,
        session_version=record.creator.session_version, session_id=session_id,
        request_id=str(getattr(request, 'request_id', ''))[:100])
    record.celery_task_id = str(record.pk)
    record.save(update_fields=['celery_task_id', 'updated_at'])
    enqueue_event('import.requested', 'import:' + str(record.pk), {'record_id': str(record.pk)}, request)
    return execution


@transaction.atomic
def resume(request, identifier):
    actor = authorize(request, 'data_io:import')
    from .resources import import_allowed
    if not has_retry_permission(actor):
        raise PermissionDenied('没有任务接续权限或用户数据范围受限')
    if not task_enabled('data_io.run_data_import'):
        raise NotFound()
    execution = ImportExecution.objects.filter(pk=identifier, record__creator=actor).first()
    if execution is None:
        if not TaskRecord.objects.filter(pk=identifier, creator=actor).exists():
            raise NotFound()
        previous = TaskRecord.objects.get(pk=identifier)
        from .resources import get_resource
        config = get_resource(previous.related_resource)
        if not config or not config['importable'] or previous.task_type != 'import':
            raise ValidationError('资源不能导入')
        from apps.files.models import FileModel
        from uuid import UUID
        try:
            source_id = UUID(str((previous.result or {}).get('file_id')))
        except (ValueError, TypeError):
            raise ValidationError('源文件已过期或不可用，请重新上传') from None
        if not FileModel.objects.filter(pk=source_id, is_deleted=False).exists():
            raise ValidationError('源文件已过期或不可用，请重新上传')
        raise ValidationError('旧任务没有逐行提交账本，不能安全接续；请检查已完成数据后重新上传')
    from apps.files.models import FileModel
    source_id = ImportBatch.objects.get(pk=execution.batch_id).source_id
    # 清理器先锁源文件；接续也先锁源，随后批次/任务，防止 FK 置空形成逆序死锁。
    source = scope_queryset(FileModel.objects.select_for_update().filter(is_deleted=False), actor, 'file', 'uploader_id', fallback='self').filter(pk=source_id).first()
    if source is None or not source.file:
        raise ValidationError('源文件已过期或不可用，请重新上传')
    batch = ImportBatch.objects.select_for_update().get(pk=execution.batch_id)
    record = TaskRecord.objects.select_for_update().get(pk=identifier)
    if record.status not in ('failed', 'cancelled') or batch.active_record_id != record.pk:
        raise ExecutionConflict()
    if execution.attempt >= 5:
        raise ValidationError('本批次已达到五次人工执行上限，请检查原因后另行提交')
    from .resources import get_resource
    config = get_resource(batch.resource)
    if not config or not config['importable']:
        raise ValidationError('资源不能导入')
    if not import_allowed(actor, batch.resource):
        raise PermissionDenied('没有该资源的导入权限或数据范围受限')
    new = TaskRecord.objects.create(name=record.name.removesuffix('（接续）')[:190] + '（接续）',
        task_type='import', related_resource=batch.resource, creator=actor, result={'file_id': str(source.pk)})
    register(new, source, request, batch, execution.attempt + 1)
    batch.active_record = new
    batch.save(update_fields=['active_record', 'updated_at'])
    write_audit(request=request, actor=actor, resource='task', identifier=new.pk, action='create',
        before=None, after=snapshot('task', new), record=new, description='接续未提交的导入行；原任务 ' + str(record.pk))
    return new


def has_retry_permission(actor):
    from apps.permissions.permissions import has_permission_code
    return has_permission_code(actor, 'task:retry')
