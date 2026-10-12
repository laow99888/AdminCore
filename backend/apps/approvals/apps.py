"""
审批流程应用配置
"""

from django.apps import AppConfig


class ApprovalsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.approvals'
    verbose_name = '审批流程'
