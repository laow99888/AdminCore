"""显式登记的历史数据保留策略；不扫描文件系统或猜测旧文件用途。"""
from datetime import timedelta
import time

from django.db import transaction
from django.db.models import CharField, Exists, OuterRef, Q, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Replace
from django.utils import timezone

from apps.core.modules import module_enabled
from apps.core.system_config import config_value
from apps.files.models import FileModel, FileStorageError
from apps.logs.models import OperationLog, LoginLog, ExceptionLog
from .models import TaskRecord

LOGS = {'operation': OperationLog, 'login': LoginLog, 'exception': ExceptionLog}
BATCH_SIZE = 100
MAX_ROWS = 1000


def policy():
    return {**{key + '_days': config_value('lifecycle.' + key + '_days')
               for key in (*LOGS, 'import')}, 'imports_enabled': module_enabled('data_io')}


def import_in_use(file_id, cutoff):
    # 任一未完成或最近使用过的导入都保护原文件；保留可重试窗口。
    return TaskRecord.objects.filter(task_type='import', result__file_id=str(file_id)).filter(
        Q(status__in=['pending', 'running']) | Q(completed_at__isnull=True)
        | Q(completed_at__gte=cutoff)).exists()


def unprotected_imports(query, cutoff):
    # SQLite 的 UUID 存储无连字符，PostgreSQL 使用原生 UUID；统一文本后做相关子查询。
    # 先排除保护中的文件再取有界批次，防止最旧的活跃任务长期饿死后续清理。
    tasks = TaskRecord.objects.filter(task_type='import').filter(
        Q(status__in=['pending', 'running']) | Q(completed_at__isnull=True)
        | Q(completed_at__gte=cutoff)).annotate(
            source_id=Replace(KeyTextTransform('file_id', 'result'), Value('-'), Value(''), output_field=CharField())
        ).filter(source_id=OuterRef('source_id'))
    return query.annotate(source_id=Replace(Cast('pk', CharField()), Value('-'), Value(''))
        ).alias(in_use=Exists(tasks)).filter(in_use=False)


def audit(record, category, identifiers):
    from apps.logs.audit import write_audit
    write_audit(actor=record.creator, action='delete', resource='lifecycle', identifier=record.pk, record=record,
                before={'category': category, 'ids': [str(pk) for pk in identifiers], 'count': len(identifiers)})


def clean(*, dry_run=False, record=None, expected_policy=None, celery_task_id=''):
    if type(dry_run) is not bool:
        raise ValueError('dry_run 必须为布尔值')
    record = record or TaskRecord.objects.create(name='清理历史日志与导入源文件', task_type='cleanup',
        status='running', started_at=timezone.now(), celery_task_id=celery_task_id,
        related_resource='maintenance:lifecycle')
    result = {'dry_run': dry_run, 'policy': {}, 'eligible': {}, 'deleted': {},
              'failed': 0, 'failures': [], 'protected_imports': 0, 'more': False}
    deadline = time.monotonic() + 180
    now = timezone.now()
    try:
        result['policy'] = policy()
        if expected_policy is not None and expected_policy != result['policy']:
            raise ValueError('preview_policy_changed')
        for category, model in LOGS.items():
            cutoff = now - timedelta(days=result['policy'][category + '_days'])
            query = model.objects.filter(created_at__lt=cutoff)
            result['eligible'][category] = query.count()
            result['deleted'][category] = 0
            if dry_run:
                continue
            while result['deleted'][category] < MAX_ROWS and time.monotonic() < deadline:
                with transaction.atomic():
                    remaining = min(BATCH_SIZE, MAX_ROWS - result['deleted'][category])
                    ids = list(query.select_for_update().order_by('created_at', 'pk').values_list('pk', flat=True)[:remaining])
                    if not ids:
                        break
                    # 删除与摘要审计同事务；审计写入失败时原日志仍在。
                    audit(record, category, ids)
                    model.objects.filter(pk__in=ids, created_at__lt=cutoff).delete()
                result['deleted'][category] += len(ids)
            result['more'] |= query.exists()
        result['eligible']['imports'] = result['deleted']['imports'] = 0
        if result['policy']['imports_enabled']:
            cutoff = now - timedelta(days=result['policy']['import_days'])
            # 过期预检的元数据也纳入已有保留策略；正式账本和接续不依赖此记录。
            from apps.data_io.models import BusinessImportPlan
            plans = BusinessImportPlan.objects.filter(expires_at__lt=cutoff)
            result['eligible']['import_plans'] = plans.count()
            result['deleted']['import_plans'] = 0
            plan_ids = list(plans.order_by('expires_at', 'pk').values_list('pk', flat=True)[:MAX_ROWS])
            result['more'] |= result['eligible']['import_plans'] > len(plan_ids)
            if not dry_run and plan_ids:
                with transaction.atomic():
                    audit(record, 'import_plans', plan_ids)
                    result['deleted']['import_plans'] = plans.filter(pk__in=plan_ids).delete()[0]
            query = FileModel.objects.filter(purpose='import', is_deleted=False, created_at__lt=cutoff)
            eligible = unprotected_imports(query, cutoff)
            result['eligible']['imports'] = eligible.count()
            result['protected_imports'] = max(0, query.count() - result['eligible']['imports'])
            # 每次最多处理 1,000 个可删除文件，锁后仍复核新入队的重试任务。
            candidates = list(eligible.order_by('created_at', 'pk').values_list('pk', flat=True)[:MAX_ROWS])
            result['more'] |= result['eligible']['imports'] > len(candidates)
            for identifier in candidates:
                if time.monotonic() >= deadline:
                    result['more'] = True
                    break
                with transaction.atomic():
                    row = query.select_for_update().filter(pk=identifier).first()
                    if not row:
                        continue
                    if import_in_use(identifier, cutoff):
                        result['protected_imports'] += 1
                        result['eligible']['imports'] -= 1
                        continue
                    if dry_run:
                        continue
                    try:
                        # 重试接口取得同一文件行锁后才登记任务，避免清理/重试竞争。
                        row.hard_delete(audit=lambda _: audit(record, 'imports', [identifier]))
                    except FileStorageError:
                        result['failed'] += 1
                        if len(result['failures']) < 20:
                            result['failures'].append({'id': str(identifier), 'code': 'storage_unavailable'})
                    else:
                        result['deleted']['imports'] += 1
        if result['failed']:
            record.result = result
            record.save(update_fields=['result', 'updated_at'])
            record.mark_failed('lifecycle_partial_failure')
        else:
            record.mark_success(result)
        return result
    except Exception as exc:
        record.result = result
        record.save(update_fields=['result', 'updated_at'])
        record.mark_failed(type(exc).__name__)
        raise
