"""
Celery 应用配置

worker 启动：celery -A config worker -l info
beat 启动：celery -A config beat -l info（调度计划存数据库，由 django-celery-beat 管理）
"""

import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('admincore')

# 配置从 Django settings 读取（CELERY_ 前缀）
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动发现各应用的 tasks.py
app.autodiscover_tasks()
