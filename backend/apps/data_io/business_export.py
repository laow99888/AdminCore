"""有界、逐批授权的业务导出；快照保存 ID/版本，不保存业务正文。"""
import csv
import hashlib
import io
import json
import logging
import tempfile
import uuid
from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace

from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.files import File
from django.db import transaction
from django.http import QueryDict
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.modules import require_task, task_enabled
from apps.core.tenancy import current_tenant_id, tenant_context
from apps.tasks.models import TaskRecord
from apps.tasks.reliability import valid_execution
from . import business
from .models import BusinessExportRequest
from .views import spreadsheet_text

MAX_DOCUMENTS = 10000
MAX_ROWS = 50000
MAX_BYTES = 50 * 1024 * 1024
BATCH_SIZE = 250
TASK_NAME = 'data_io.run_business_export'
logger = logging.getLogger(__name__)


def columns_for(actor, resource, schema):
    readable = business.fields_for(actor, resource, 'read')
    columns = [field['name'] for field in schema['fields'] if field['name'] in readable]
    for group in schema['details']:
        if group['name'] in readable:
            columns.extend(group['name'] + '.' + field['name'] for field in group['fields']
                           if group['name'] + '.' + field['name'] in readable)
    if not columns:
        raise PermissionDenied('当前角色没有该资源的字段读取权限')
    return columns


def filtered(actor, resource, params):
    schema, _, service = business.require(actor, resource, export=True)
    if (not isinstance(params, dict) or len(params) > 40
            or any(not isinstance(key, str) or not isinstance(value, str) or len(value) > 8000
                   for key, value in params.items()) or set(params) & {'page', 'page_size', 'format'}):
        raise ValidationError('导出筛选参数无效')
    query = QueryDict('', mutable=True)
    query.update(params)
    view = import_module('apps.' + resource + '.views').RecordViewSet()
    view.action, view.request, view.format_kwarg = 'list', SimpleNamespace(user=actor, query_params=query), None
    from apps.core.list_queries import validate_list_query
    validate_list_query(view.request, view)
    # 平台管理员没有选择租户时只导出全局记录，不将多个租户混为一份快照。
    queryset = service.visible(actor).filter(tenant_id=current_tenant_id())
    return schema, view.filter_queryset(queryset)


def prepare(actor, resource, params, format_name):
    if format_name not in ('csv', 'xlsx') or not task_enabled(TASK_NAME):
        raise ValidationError('异步导出格式无效或任务未启用')
    schema, queryset = filtered(actor, resource, params)
    columns = columns_for(actor, resource, schema)
    snapshot = [{'id': str(identifier), 'version': version}
                for identifier, version in queryset.values_list('pk', 'version')[:MAX_DOCUMENTS + 1]]
    if len(snapshot) > MAX_DOCUMENTS:
        raise ValidationError('异步导出最多10000单，请缩小筛选范围')
    return {'filters': params, 'columns': columns, 'format': format_name,
            'schema_digest': business.schema_digest(schema)}, snapshot


def checked_actor(execution, *, lock=False):
    users = get_user_model().objects
    if lock:
        users = users.select_for_update()
    actor = users.filter(pk=execution.record.creator_id).first()
    if lock and execution.session_id:
        from apps.auth_app.models import AuthSession
        AuthSession.objects.select_for_update().filter(pk=execution.session_id).first()
    if lock and execution.tenant_id:
        # 租户状态管理不必锁定每个成员用户；持有租户行，覆盖本批次/下载复核。
        from apps.core.models import Tenant
        Tenant.objects.select_for_update().filter(pk=execution.tenant_id).first()
    if (not valid_execution(execution, actor) or not task_enabled(TASK_NAME)
            or str(current_tenant_id()) != str(execution.tenant_id)):
        raise PermissionDenied('导出授权已撤销，请重新提交')
    schema, _ = filtered(actor, execution.resource, execution.options['filters'])
    if (business.schema_digest(schema) != execution.options['schema_digest']
            or not set(execution.options['columns']) <= set(columns_for(actor, execution.resource, schema))):
        raise PermissionDenied('导出定义或字段授权已变化，请重新提交')
    return actor, schema


def text(value):
    result = str('' if value is None else value.isoformat() if hasattr(value, 'isoformat') else value)
    if len(result) > 32767 or any(ord(char) < 32 and char not in '\t\r\n' for char in result):
        raise ValidationError('导出包含无效单元格')
    return result


def document_rows(row, schema, columns):
    """按各组 position/id 顺序横向对齐；不连接明细表，不产生笛卡尔积。"""
    fields = {field['name']: field for field in schema['fields']}
    groups = {group['name']: group for group in schema['details']}
    children = {name: list(getattr(row, name).all()) for name in groups
                if any(column.startswith(name + '.') for column in columns)}
    count = max([1, *(len(values) for values in children.values())])
    result, content_size = [], 0
    for index in range(count):
        values = []
        for column in columns:
            if '.' in column:
                group, name = column.split('.')
                spec = next(field for field in groups[group]['fields'] if field['name'] == name)
                instance = children[group][index] if index < len(children[group]) else None
            else:
                name, spec, instance = column, fields[column], row
            attribute = name + ('_id' if spec['kind'] in {'relation', 'file'} else '')
            values.append(text(getattr(instance, attribute)) if instance is not None else '')
        content_size += sum(len(value.encode('utf-8')) for value in values)
        if len(result) >= MAX_ROWS or content_size > MAX_BYTES:
            raise ValidationError('异步导出超过50000展开行或50 MiB，请缩小范围')
        result.append(values)
    return result


def read_batch(execution, actor, schema, snapshot, *, verify_hash=False):
    _, queryset = filtered(actor, execution.resource, execution.options['filters'])
    groups = [group['name'] for group in schema['details']
              if any(column.startswith(group['name'] + '.') for column in execution.options['columns'])]
    # 所有受支持的整单修改先锁主记录；读取同一锁，避免主版本和明细跨事务混合。
    rows = queryset.filter(pk__in=[item['id'] for item in snapshot]).order_by('pk')
    rows = rows.select_for_update(of=('self',)).prefetch_related(*groups)
    found = {str(row.pk): row for row in rows}
    output, content_size = [], 0
    for item in snapshot:
        row = found.get(item['id'])
        if row is None or row.version != item['version']:
            raise ValidationError('导出记录已变化或不可访问，请重新提交')
        values = document_rows(row, schema, execution.options['columns'])
        digest = hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        if verify_hash and digest != item.get('digest'):
            raise ValidationError('导出记录已变化或不可访问，请重新提交')
        item['digest'] = digest
        content_size += sum(len(value.encode('utf-8')) for row_values in values for value in row_values)
        if len(output) + len(values) > MAX_ROWS or content_size > MAX_BYTES:
            raise ValidationError('异步导出超过50000展开行或50 MiB，请缩小范围')
        output.extend(values)
    return output


def guarded_batch(execution, snapshot, *, verify_hash=False):
    with transaction.atomic():
        actor, schema = checked_actor(execution, lock=True)
        record = TaskRecord.objects.select_for_update().get(pk=execution.pk)
        if record.status != ('success' if verify_hash else 'running'):
            raise ValidationError('导出任务已停止或尚未完成')
        if (timezone.now() >= execution.expires_at or not verify_hash and
                timezone.now() >= record.started_at + timedelta(seconds=execution.policy['soft_timeout'])):
            raise ValidationError('导出已过期或超时，请重新提交')
        return read_batch(execution, actor, schema, snapshot, verify_hash=verify_hash)


def write_artifact(execution, target):
    columns, format_name = execution.options['columns'], execution.options['format']
    book, saved = None, False
    if format_name == 'csv':
        stream = io.TextIOWrapper(target, encoding='utf-8-sig', newline='', write_through=True)
        writer = csv.writer(stream)
        writer.writerow(columns)
        append = writer.writerow
    else:
        from openpyxl import Workbook
        book = Workbook(write_only=True)
        sheet = book.create_sheet('export')
        sheet.append(columns)
        append = sheet.append
    count, content_size = 0, 0
    try:
        for start in range(0, len(execution.snapshot), BATCH_SIZE):
            rows = guarded_batch(execution, execution.snapshot[start:start + BATCH_SIZE])
            for row in rows:
                count += 1
                content_size += sum(len(value.encode('utf-8')) for value in row)
                if count > MAX_ROWS or content_size > MAX_BYTES:
                    raise ValidationError('异步导出超过50000展开行或50 MiB，请缩小范围')
                append([spreadsheet_text(value) for value in row])
                if format_name == 'csv' and target.tell() > MAX_BYTES:
                    raise ValidationError('异步导出超过50000展开行或50 MiB，请缩小范围')
            TaskRecord.objects.filter(pk=execution.pk, status='running').update(
                progress=min(99, int(min(start + BATCH_SIZE, len(execution.snapshot)) * 100 / max(1, len(execution.snapshot)))),
                result={'documents': min(start + BATCH_SIZE, len(execution.snapshot)), 'rows': count}, updated_at=timezone.now())
        if book:
            book.save(target)
            saved = True
        else:
            stream.flush()
        if target.tell() > MAX_BYTES:
            raise ValidationError('异步导出超过50000展开行或50 MiB，请缩小范围')
        return count
    finally:
        if book:
            if not saved:
                # write_only 工作表使用临时 XML；有界校验失败也要完成一次保存以回收它。
                # 输出仍在调用者的临时文件中，异常路径不会发布产物。
                try:
                    book.save(target)
                except Exception:
                    logger.warning('Business export workbook cleanup failed')
            book.close()
        else:
            stream.detach()  # 调用者拥有底层临时文件。


@shared_task(bind=True, name=TASK_NAME, soft_time_limit=300, time_limit=330,
             acks_late=True, reject_on_worker_lost=True)
def run_business_export(self, record_id):
    require_task(self.name)
    execution = BusinessExportRequest.objects.select_related('record').filter(pk=record_id).first()
    if execution is None:
        return {'skipped': True}
    with tenant_context(execution.tenant_id):
        with transaction.atomic():
            record = TaskRecord.objects.select_for_update().get(pk=record_id)
            if not record.mark_started():
                return {'skipped': True}
        artifact_name = None
        try:
            if record.created_at < timezone.now() - timedelta(seconds=execution.policy['queue_expiry']):
                raise ValidationError('导出已过期或超时，请重新提交')
            # 空结果也必须复核身份，不能跳过循环后直接成功。
            checked_actor(execution)
            with tempfile.TemporaryFile(mode='w+b') as target:
                count = write_artifact(execution, target)
                target.seek(0)
                digest = hashlib.file_digest(target, 'sha256').hexdigest()
                target.seek(0)
                with transaction.atomic():
                    checked_actor(execution, lock=True)
                    locked = TaskRecord.objects.select_for_update().get(pk=record_id)
                    if locked.status != 'running':
                        return {'stopped': True}
                    if (timezone.now() >= execution.expires_at or timezone.now() >=
                            locked.started_at + timedelta(seconds=execution.policy['soft_timeout'])):
                        raise ValidationError('导出已过期或超时，请重新提交')
                    execution.artifact.save(uuid.uuid4().hex + '.' + execution.options['format'], File(target), save=False)
                    artifact_name = execution.artifact.name
                    execution.artifact_sha256 = digest
                    execution.save(update_fields=['artifact', 'artifact_sha256', 'snapshot', 'updated_at'])
                    locked.mark_success({'documents': len(execution.snapshot), 'rows': count,
                                         'expires_at': execution.expires_at.isoformat()})
            return {'documents': len(execution.snapshot), 'rows': count}
        except Exception as exc:
            if artifact_name:
                execution.artifact.storage.delete(artifact_name)
            record.mark_failed('business_export_' + type(exc).__name__)
            logger.warning('Business export failed: record=%s error=%s', record_id, type(exc).__name__)
            return {'failed': True}


def recover_lost_exports(limit=100):
    """过期产物清理、入队失联终止；导出无业务写入，用户可重新提交。"""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('导出清理批量范围为1-1000')
    rows = BusinessExportRequest.all_objects.select_related('record').filter(
        record__status__in=['pending', 'running']).order_by('created_at')[:limit]
    for execution in rows:
        record, current, now = execution.record, execution.policy, timezone.now()
        due = (record.created_at + timedelta(seconds=current['queue_expiry']) if record.status == 'pending'
               else record.started_at + timedelta(seconds=current['hard_timeout'] + 60))
        if due < now:
            with transaction.atomic(), tenant_context(execution.tenant_id):
                locked = TaskRecord.objects.select_for_update().get(pk=record.pk)
                if locked.status == record.status:
                    locked.mark_failed('business_export_worker_lost_or_expired')
    expired = BusinessExportRequest.all_objects.filter(expires_at__lte=timezone.now()).exclude(artifact='')[:limit]
    for execution in expired:
        # 先删私有存储再清空引用；存储错误保留引用，下一轮重试。
        execution.artifact.delete(save=False)
        BusinessExportRequest.all_objects.filter(pk=execution.pk).update(artifact='', artifact_sha256='')
