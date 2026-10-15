"""
通知系统应用配置
"""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.notifications'
    verbose_name = '通知中心'

    def ready(self):
        from .external_channels import validate_configuration
        validate_configuration()
