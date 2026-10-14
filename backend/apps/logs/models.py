"""
日志系统模型
"""

from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel

User = get_user_model()


class OperationLog(BaseModel):
    """操作日志"""
    ACTION_CHOICES = [
        ('create', '创建'),
        ('read', '查看'),
        ('update', '修改'),
        ('delete', '删除'),
        ('export', '导出'),
        ('import', '导入'),
        ('download', '下载'),
        ('upload', '上传'),
        ('login', '登录'),
        ('logout', '登出'),
        ('other', '其他'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='操作用户')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, verbose_name='操作类型')
    resource = models.CharField(max_length=100, verbose_name='资源类型')  # 如 'user', 'role' 等
    resource_id = models.CharField(max_length=100, blank=True, verbose_name='资源 ID')
    description = models.TextField(blank=True, verbose_name='描述')
    ip_address = models.GenericIPAddressField(verbose_name='IP 地址')
    user_agent = models.TextField(blank=True, verbose_name='用户代理')
    status = models.IntegerField(default=200, verbose_name='状态码')
    actor_identifier = models.CharField(max_length=100, blank=True, editable=False)
    request_id = models.CharField(max_length=100, blank=True, db_index=True, editable=False)
    task_id = models.CharField(max_length=100, blank=True, db_index=True, editable=False)
    task_record_id = models.UUIDField(null=True, blank=True, db_index=True, editable=False)
    audit_version = models.PositiveSmallIntegerField(default=0, editable=False)
    before_values = models.JSONField(null=True, blank=True, editable=False)
    after_values = models.JSONField(null=True, blank=True, editable=False)
    batch_results = models.JSONField(default=list, blank=True, editable=False)

    class Meta:
        verbose_name = '操作日志'
        verbose_name_plural = '操作日志'
        indexes = [
            models.Index(fields=['user', 'action']),
            models.Index(fields=['resource', 'action']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.user.username if self.user else 'Unknown'} - {self.action} - {self.resource}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            from .context import request_id
            from celery import current_task
            self.actor_identifier = self.actor_identifier or str(self.user_id or '')
            self.request_id = self.request_id or request_id.get()
            self.task_id = self.task_id or str(getattr(getattr(current_task, 'request', None), 'id', '') or '')
        return super().save(*args, **kwargs)


class LoginLog(BaseModel):
    """登录日志"""
    STATUS_CHOICES = [
        ('success', '成功'),
        ('failed', '失败'),
        ('locked', '被锁定'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='用户')
    username = models.CharField(max_length=100, verbose_name='用户名')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name='登录状态')
    ip_address = models.GenericIPAddressField(verbose_name='IP 地址')
    user_agent = models.TextField(blank=True, verbose_name='用户代理')
    error_message = models.TextField(blank=True, verbose_name='错误信息')

    class Meta:
        verbose_name = '登录日志'
        verbose_name_plural = '登录日志'
        indexes = [
            models.Index(fields=['username', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.username} - {self.status}"


class ExceptionLog(BaseModel):
    """异常日志"""
    LEVEL_CHOICES = [
        ('debug', 'DEBUG'),
        ('info', 'INFO'),
        ('warning', 'WARNING'),
        ('error', 'ERROR'),
        ('critical', 'CRITICAL'),
    ]

    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, verbose_name='日志级别')
    message = models.TextField(verbose_name='错误信息')
    traceback = models.TextField(verbose_name='堆栈跟踪')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='用户')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP 地址')
    request_path = models.CharField(max_length=200, blank=True, verbose_name='请求路径')
    request_method = models.CharField(max_length=20, blank=True, verbose_name='请求方法')

    class Meta:
        verbose_name = '异常日志'
        verbose_name_plural = '异常日志'
        indexes = [
            models.Index(fields=['level', 'created_at']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.level} - {self.message[:50]}"
