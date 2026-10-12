"""
AdminCore 项目包

导入 Celery 应用，确保 @shared_task 装饰器使用当前实例。
"""

from .celery import app as celery_app

__all__ = ('celery_app',)
