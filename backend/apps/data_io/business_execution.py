"""业务导入沿用设备授权、逐行账本及接续，写入使用原业务事务与扩展。"""
import hashlib
from datetime import timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError, DataError
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.core.modules import task_enabled
from apps.files.access import file_queryset_for_actor
from apps.files.models import FileModel
from apps.tasks.models import ImportBatch, ImportRowReceipt, TaskRecord
from apps.tasks.reliability import valid_execution
from .business import (require, options_for, parse_rows, serialized_values, schema_digest, import_units,
                       business_summary, MAX_BYTES)


class PreviewRecordChanged(Exception):
    pass


def run_business_import(task_name, record, execution):
    from apps.core.tenancy import enabled, tenant_context
    if enabled():
        batch = execution.batch
        if record.tenant_id != batch.tenant_id or execution.tenant_id != batch.tenant_id or batch.source.tenant_id != batch.tenant_id:
            record.mark_failed('import_tenant_mismatch')
            return
        with tenant_context(batch.tenant_id):
            return _run_business_import(task_name, record, execution)
    return _run_business_import(task_name, record, execution)


def _run_business_import(task_name, record, execution):
    with transaction.atomic():
        batch = ImportBatch.objects.select_for_update().get(pk=execution.batch_id)
        if batch.active_record_id != record.pk or not record.mark_started():
            return {'skipped': True}
    total = len(batch.options.get('rows', []))
    try:
        current = execution.policy
        if record.created_at < timezone.now() - timedelta(seconds=current['queue_expiry']):
            record.mark_failed('queue_expired')
            return
        actor = get_user_model().objects.filter(pk=record.creator_id).first()
        if not valid_execution(execution, actor):
            raise PermissionError()
        schema, _, service = require(actor, batch.resource, batch.options['mode'])
        source = file_queryset_for_actor(FileModel.objects.filter(is_deleted=False), actor).filter(pk=batch.source_id).first()
        if source is None or not source.file:
            record.mark_failed('import_source_unavailable')
            return
        with source.file.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != batch.source_sha256:
            record.mark_failed('import_source_changed')
            return
        headers, rows = parse_rows(raw, source.original_name)
        units = import_units(schema, rows, batch.options)
        if (len(units) != total or schema_digest(schema) != batch.options['schema_digest']
                or any(unit['source_rows'] != planned.get('source_rows', [planned['row']])
                       for unit, planned in zip(units, batch.options['rows']))):
            record.mark_failed('import_definition_changed')
            return
        for index, unit in enumerate(units):
            row = unit['source']
            with transaction.atomic():
                actor = get_user_model().objects.select_for_update().filter(pk=record.creator_id).first()
                if execution.session_id:
                    from apps.auth_app.models import AuthSession
                    AuthSession.objects.select_for_update().filter(pk=execution.session_id).first()
                if execution.tenant_id:
                    # 与后台导出同序：租户关闭必须排在本单提交之前或之后。
                    from apps.core.models import Tenant
                    Tenant.objects.select_for_update().filter(pk=execution.tenant_id).first()
                batch = ImportBatch.objects.select_for_update().get(pk=execution.batch_id)
                locked = TaskRecord.objects.select_for_update().get(pk=record.pk)
                if locked.status != 'running' or batch.active_record_id != record.pk:
                    return {'stopped': True}
                try:
                    if not task_enabled(task_name) or not valid_execution(execution, actor):
                        raise PermissionError()
                    require(actor, batch.resource, batch.options['mode'])
                    options = options_for(actor, batch.resource,
                        {key: batch.options[key] for key in ('mapping', 'key', 'mode')}, headers)
                except (APIException, PermissionError):
                    TaskRecord.objects.filter(pk=record.pk).update(result=business_summary(batch, total))
                    locked.mark_failed('execution_not_authorized_committed_rows_preserved')
                    return
                if timezone.now() > locked.started_at + timedelta(seconds=current['soft_timeout']):
                    TaskRecord.objects.filter(pk=record.pk).update(result=business_summary(batch, total))
                    locked.mark_failed('task_timeout_committed_rows_preserved')
                    return
                number = unit['source_rows'][0]
                if ImportRowReceipt.objects.filter(batch=batch, row=number).exists():
                    continue
                planned = batch.options['rows'][index]
                outcome, error = planned['action'], planned['error']
                if outcome in ('created', 'updated'):
                    try:
                        with transaction.atomic():
                            instance = None
                            if outcome == 'updated':
                                instance = service.visible(actor).select_for_update(of=('self',)).filter(pk=planned['identifier']).first()
                                if instance is None or instance.version != planned['version']:
                                    raise PreviewRecordChanged()
                            values = serialized_values(actor, schema, row, options,
                                version=planned['version'], instance=instance)
                            service.mutate(SimpleNamespace(user=actor, auth=None, request_id=execution.request_id, task_record=locked),
                                'update' if instance else 'create', values, instance.pk if instance else None)
                    except PreviewRecordChanged:
                        outcome, error = 'failed', 'record_changed'
                    except (APIException, IntegrityError, DataError):
                        outcome, error = 'failed', 'row_validation_failed'
                ImportRowReceipt.objects.create(tenant=batch.tenant, batch=batch, row=number,
                    created=outcome in ('created', 'updated'), outcome=outcome, error=error)
                if index == 0 or (index + 1) % 50 == 0 or index + 1 == total:
                    TaskRecord.objects.filter(pk=record.pk, status='running').update(
                        result=business_summary(batch, total), progress=min(99, int((index + 1) * 100 / max(1, total))))
        record.mark_success(business_summary(batch, total))
        return record.result
    except PermissionError:
        record.mark_failed('execution_not_authorized')
    except APIException:
        record.mark_failed('import_validation_failed')
    except Exception as exc:
        TaskRecord.objects.filter(pk=record.pk, status='running').update(result=business_summary(batch, total))
        record.mark_failed(type(exc).__name__)
        raise
