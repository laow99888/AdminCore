"""
数据导入异步任务
"""

import logging

from celery import shared_task
from apps.tasks.routing import RegisteredPolicyTask
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from uuid import uuid4
from datetime import timedelta
from kombu.exceptions import OperationalError

logger = logging.getLogger(__name__)


def dispatch_task(func, *args):
    """派发 Celery 任务；broker 不可用时降级为同步执行（开发/无 Redis 环境）"""
    from apps.tasks.models import TaskRecord
    task_id = str(uuid4())
    TaskRecord.objects.filter(pk=args[0], status='pending').update(celery_task_id=task_id)
    try:
        result = func.apply_async(args=args, task_id=task_id)
        return result.id or task_id
    except OperationalError as exc:
        if not settings.DEBUG:
            TaskRecord.objects.filter(pk=args[0], status='pending').update(status='failed', error='任务队列不可用')
            raise
        logger.warning('Celery broker 不可用（%s），任务改为同步执行', exc)
        func(*args)
        return ''


@shared_task(bind=True, name='data_io.run_data_import', soft_time_limit=300, time_limit=330,
             acks_late=True, reject_on_worker_lost=True, base=RegisteredPolicyTask)
def run_data_import(self, task_record_id):
    """重复投递只领取一次；SQL 行提交与账本同事务，人工接续不重复创建。"""
    from apps.core.modules import require_task, task_enabled
    require_task(self.name)
    import pandas as pd
    import io
    from django.contrib.auth import get_user_model
    from apps.files.models import FileModel
    from apps.tasks.models import TaskRecord, ImportExecution, ImportBatch, ImportRowReceipt
    from apps.tasks.reliability import policy, valid_execution
    from apps.core.data_scope import scope_queryset
    from apps.permissions.permissions import has_permission_code
    from .resources import get_resource, import_allowed
    from .execution import digest
    record = TaskRecord.objects.filter(pk=task_record_id).first()
    if record is None or record.status != 'pending':
        return {'skipped': True}
    execution = ImportExecution.objects.filter(pk=record.pk).first()
    if execution is None:
        # 兼容旧在途任务：首次执行前生成账本，不允许旧失败任务盲目重试。
        with transaction.atomic():
            locked = TaskRecord.objects.select_for_update().get(pk=record.pk)
            if locked.status != 'pending':
                return {'skipped': True}
            actor = get_user_model().objects.filter(pk=record.creator_id, is_active=True).first()
            if actor is None or actor.must_change_password or not has_permission_code(actor, 'data_io:import'):
                record.mark_failed('execution_not_authorized')
                return
            config = get_resource(record.related_resource)
            if not config or not config['importable']:
                record.mark_failed('import_resource_unavailable')
                return
            if not import_allowed(actor, record.related_resource):
                record.mark_failed('execution_not_authorized')
                return
            source = scope_queryset(FileModel.objects.filter(is_deleted=False), actor, 'file', 'uploader_id', fallback='self').filter(
                pk=(record.result or {}).get('file_id')).first() if actor else None
            if not source or not source.file:
                record.mark_failed('import_source_unavailable')
                return
            batch = ImportBatch.objects.create(source=source, source_sha256=digest(source.file),
                                              resource=record.related_resource, active_record=record)
            execution = ImportExecution.objects.create(record=record, batch=batch, policy=policy('import'),
                                                       session_version=actor.session_version)
    with transaction.atomic():
        batch = ImportBatch.objects.select_for_update().get(pk=execution.batch_id)
        if batch.active_record_id != record.pk or not record.mark_started():
            return {'skipped': True}
    summary = None
    try:
        current = execution.policy
        if record.created_at < timezone.now() - timedelta(seconds=current['queue_expiry']):
            record.mark_failed('queue_expired')
            return
        actor = get_user_model().objects.filter(pk=record.creator_id).first()
        if not valid_execution(execution, actor) or not import_allowed(actor, batch.resource):
            record.mark_failed('execution_not_authorized')
            return
        config = get_resource(batch.resource)
        if not config or not config['importable']:
            record.mark_failed('import_resource_unavailable')
            return
        source = scope_queryset(FileModel.objects.filter(is_deleted=False), actor, 'file', 'uploader_id', fallback='self').filter(pk=batch.source_id).first()
        if not source or not source.file:
            record.mark_failed('import_source_unavailable')
            return
        # 对实际读取的字节验证，不在哈希与解析之间重新打开产生 TOCTOU。
        with source.file.open('rb') as stream:
            raw = stream.read(10 * 1024 * 1024 + 1)
        import hashlib
        if len(raw) > 10 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != batch.source_sha256:
            record.mark_failed('import_source_changed')
            return
        source_bytes = io.BytesIO(raw)
        frame = (pd.read_csv(source_bytes, dtype=str, nrows=5001) if source.file.name.lower().endswith('.csv')
                 else pd.read_excel(source_bytes, dtype=str, nrows=5001)).fillna('')
        if len(frame) > 5000:
            record.mark_failed('import_row_limit_5000')
            return
        if any(field not in frame.columns for field in config['required']):
            record.mark_failed('import_missing_columns')
            return
        fields = config.get('import_fields', config['fields'])
        if set(frame.columns) - set(fields):
            record.mark_failed('import_unknown_columns')
            return
        total = len(frame)
        summary = import_summary(batch, source.pk, total)
        for index, row in frame.iterrows():
            data = {field: str(row.get(field, '')).strip() for field in fields}
            with transaction.atomic():
                # 锁用户和原设备，再锁批次和执行；与撤销/取消/接续同一顺序。
                actor = get_user_model().objects.select_for_update().filter(pk=record.creator_id).first()
                if execution.session_id:
                    from apps.auth_app.models import AuthSession
                    AuthSession.objects.select_for_update().filter(pk=execution.session_id).first()
                batch = ImportBatch.objects.select_for_update().get(pk=execution.batch_id)
                locked = TaskRecord.objects.select_for_update().get(pk=record.pk)
                if locked.status != 'running' or batch.active_record_id != record.pk:
                    return {'stopped': True}
                if (not task_enabled(self.name) or not valid_execution(execution, actor)
                        or not import_allowed(actor, batch.resource)):
                    TaskRecord.objects.filter(pk=locked.pk, status='running').update(result=import_summary(batch, source.pk, total))
                    locked.mark_failed('execution_not_authorized_committed_rows_preserved')
                    return
                if timezone.now() > locked.started_at + timedelta(seconds=current['soft_timeout']):
                    TaskRecord.objects.filter(pk=locked.pk, status='running').update(result=import_summary(batch, source.pk, total))
                    locked.mark_failed('task_timeout_committed_rows_preserved')
                    return
                if not ImportRowReceipt.objects.filter(batch=batch, row=index + 2).exists():
                    missing = [field for field in config['required'] if not data.get(field)]
                    if missing or any(len(value) > 32767 for value in data.values()):
                        obj, error = None, 'required_or_cell_length_invalid'
                    else:
                        from django.core.exceptions import ValidationError
                        from django.db import IntegrityError, DataError
                        from rest_framework.exceptions import ValidationError as APIValidationError
                        try:
                            # 唯一键并发或行校验失败只回滚本行，不破坏外层账本事务。
                            with transaction.atomic():
                                obj, error = config['create_row'](data)
                        except (ValidationError, APIValidationError, IntegrityError, DataError):
                            obj, error = None, 'row_validation_failed'
                        if obj is not None:
                            from apps.logs.audit import write_audit, snapshot
                            resource = {'users': 'user', 'roles': 'role', 'posts': 'post'}[batch.resource]
                            write_audit(actor=actor, resource=resource, identifier=obj.pk,
                                action='create', after=snapshot(resource, obj), record=locked, origin=execution.request_id,
                                description='import_row_created')
                    # 仅保留受控错误码，不写原始姓名、邮箱或供应商错误。
                    ImportRowReceipt.objects.create(batch=batch, row=index + 2, created=obj is not None,
                                                    error='row_validation_failed' if error else '')
                    summary['processed'] += 1
                    summary['created' if obj is not None else 'failed'] += 1
                    if obj is None and len(summary['errors']) < 100:
                        summary['errors'].append({'row': index + 2, 'message': 'row_validation_failed'})
                # 账本逐行提交；显示进度至多每 50 行刷新，取消/撤权仍逐行检查。
                if index == 0 or (index + 1) % 50 == 0 or index + 1 == total:
                    TaskRecord.objects.filter(pk=record.pk, status='running').update(
                        result=summary, progress=min(99, int((index + 1) * 100 / max(1, total))), updated_at=timezone.now())
        record.mark_success(summary)
        return record.result
    except Exception as exc:
        if summary is not None:
            # 行事务可能在更新内存计数后回滚，终态必须以已提交账本重建。
            TaskRecord.objects.filter(pk=record.pk, status='running').update(result=import_summary(batch, source.pk, total))
        record.mark_failed(type(exc).__name__)
        logger.error('Import execution failed: record=%s error=%s', record.pk, type(exc).__name__)
        raise


def import_summary(batch, source_id, total):
    from apps.tasks.models import ImportRowReceipt
    receipts = ImportRowReceipt.objects.filter(batch=batch)
    errors = receipts.filter(created=False).order_by('row')
    return {'file_id': str(source_id), 'total': total, 'created': receipts.filter(created=True).count(),
            'failed': errors.count(), 'processed': receipts.count(),
            'errors': [{'row': row.row, 'message': row.error} for row in errors[:100]]}
