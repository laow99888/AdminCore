"""
核心应用配置
"""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = '核心应用'

    def ready(self):
        from . import schema  # noqa: F401 -- 注册 OpenAPI 扩展  # 注册自定义 JWT schema 扩展
