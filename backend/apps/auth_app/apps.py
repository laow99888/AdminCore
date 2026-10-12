"""
认证应用配置
"""

from django.apps import AppConfig


class AuthAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.auth_app'
    verbose_name = '认证系统'
