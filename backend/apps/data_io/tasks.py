"""
数据导入异步任务
"""

import logging

from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from uuid import uuid4
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


@shared_task(bind=True, name='data_io.run_data_import')
def run_data_import(self, task_record_id):
    """执行数据导入：解析文件 -> 逐行校验并创建 -> 记录行级错误与统计"""
    import pandas as pd
    from django.core.files.storage import default_storage

    from apps.files.models import FileModel
    from apps.tasks.models import TaskRecord
    from .resources import get_resource

    record = TaskRecord.objects.filter(id=task_record_id).first()
    if record is None:
        logger.error('Import task record %s not found', task_record_id)
        return

    claimed = TaskRecord.objects.filter(pk=record.pk, status='pending').update(
        status='running', started_at=timezone.now(), updated_at=timezone.now())
    if not claimed:
        return
    record.refresh_from_db()

    try:
        from apps.permissions.permissions import has_permission_code
        if not has_permission_code(record.creator, 'data_io:import'):
            record.mark_failed(error='任务发起人的导入权限已撤销')
            return
        config = get_resource(record.related_resource)
        if config is None:
            record.mark_failed(error=f'未注册的导入资源：{record.related_resource}')
            return

        file_record = FileModel.objects.filter(id=record.result.get('file_id') if record.result else None).first()
        if file_record is None or not file_record.file:
            record.mark_failed(error='导入文件不存在或已被删除')
            return

        with default_storage.open(file_record.file.name) as f:
            if file_record.file.name.lower().endswith('.csv'):
                df = pd.read_csv(f, dtype=str).fillna('')
            else:
                df = pd.read_excel(f, dtype=str).fillna('')

        # 列校验：必需列必须全部存在
        missing = [col for col in config['required'] if col not in df.columns]
        if missing:
            record.mark_failed(error=f'缺少必需列：{", ".join(missing)}（请下载导入模板）')
            return

        created, errors = 0, []
        total = len(df)
        for index, row in df.iterrows():
            if not TaskRecord.objects.filter(pk=record.pk, status='running').exists():
                return
            row_num = index + 2  # Excel 第 1 行是表头
            data = {field: str(row.get(field, '')).strip() for field in config['fields']}

            # 必填校验
            blank = [f for f in config['required'] if not data.get(f)]
            if blank:
                errors.append({'row': row_num, 'message': f"必填字段为空：{', '.join(blank)}"})
                continue

            with transaction.atomic():
                locked = TaskRecord.objects.select_for_update().get(pk=record.pk)
                if locked.status != 'running':
                    return
                obj, err = config['create_row'](data)
            if err:
                errors.append({'row': row_num, 'message': err})
            else:
                created += 1

            # 进度按 10% 更新
            if total and (index + 1) % max(1, total // 10) == 0:
                TaskRecord.objects.filter(id=record.id, status='running').update(
                    progress=min(99, int((index + 1) * 100 / total)))

        record.mark_success(result={
            'file_id': str(file_record.id),
            'total': total,
            'created': created,
            'failed': len(errors),
            # 错误明细最多保留 100 条，避免超大结果
            'errors': errors[:100],
        })
        logger.info('Import %s done: %d created, %d failed', record.related_resource, created, len(errors))
        return {'created': created, 'failed': len(errors)}

    except Exception as exc:
        record.mark_failed(error=f'导入执行失败：{exc}')
        logger.exception('Data import task failed')
        raise
