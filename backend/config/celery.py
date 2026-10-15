"""
Celery 应用配置

worker 启动：celery -A config worker -l info
beat 启动：celery -A config beat -l info（调度计划存数据库，由 django-celery-beat 管理）
"""

import os
import logging
import logging.config
import time

from celery import Celery
from celery.signals import setup_logging, task_prerun, task_postrun

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('admincore')

# 配置从 Django settings 读取（CELERY_ 前缀）
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动发现各应用的 tasks.py
app.autodiscover_tasks()


@setup_logging.connect
def configure_worker_logging(**kwargs):
    from django.conf import settings
    logging.config.dictConfig(settings.LOGGING)


@task_prerun.connect
def begin_task_context(task_id=None, task=None, **kwargs):
    from apps.logs.context import request_id, task_id as current_task_id, correlation_id
    headers = getattr(task.request, 'headers', None) or {}
    origin = correlation_id(headers.get('request_id')) if isinstance(headers, dict) else ''
    task.request._admincore_context = (request_id.set(origin),
                                      current_task_id.set(correlation_id(task_id)), time.monotonic())
    logging.getLogger(__name__).info('Task started', extra={'event': 'task.started'})


@task_postrun.connect
def end_task_context(task=None, state=None, **kwargs):
    from apps.logs.context import request_id, task_id as current_task_id
    context = getattr(task.request, '_admincore_context', None)
    if context is None:
        return
    try:
        logging.getLogger(__name__).info('Task finished', extra={'event': 'task.finished',
            'task_state': state,
            'duration_ms': (time.monotonic() - context[2]) * 1000})
    finally:
        request_id.reset(context[0])
        current_task_id.reset(context[1])
        del task.request._admincore_context
