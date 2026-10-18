"""
数据导入导出应用配置
"""

from django.apps import AppConfig


class DataIOConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.data_io'
    verbose_name = '数据导入导出'

    def ready(self):
        from . import signals  # noqa: F401
