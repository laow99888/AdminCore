"""
任务调度应用模型
"""

from django.db import models
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel

User = get_user_model()


class TaskRecord(BaseModel):
    """异步任务执行记录（任务中心数据来源）"""
    TYPE_CHOICES = [
        ('import', '数据导入'),
        ('export', '数据导出'),
        ('backup', '数据备份'),
        ('cleanup', '数据清理'),
        ('notification', '通知发送'),
        ('other', '其他'),
    ]
    STATUS_CHOICES = [
        ('pending', '等待执行'),
        ('running', '执行中'),
        ('success', '成功'),
        ('failed', '失败'),
        ('cancelled', '已取消'),
    ]

    name = models.CharField(max_length=200, verbose_name='任务名称')
    task_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='other', verbose_name='任务类型')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    celery_task_id = models.CharField(max_length=255, blank=True, verbose_name='Celery 任务 ID')
    progress = models.IntegerField(default=0, verbose_name='进度（0-100）')
    result = models.JSONField(null=True, blank=True, verbose_name='执行结果')
    error = models.TextField(blank=True, verbose_name='错误信息')
    related_resource = models.CharField(max_length=100, blank=True, verbose_name='关联资源')
    creator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks', verbose_name='创建者')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')

    class Meta:
        verbose_name = '任务记录'
        verbose_name_plural = '任务记录'
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['task_type']),
        ]
        constraints = [models.UniqueConstraint(fields=['related_resource'],
            condition=models.Q(related_resource='maintenance:backup', status__in=['pending', 'running']),
            name='one_unfinished_backup')]

    def __str__(self):
        return f'{self.name} [{self.status}]'

    def mark_started(self):
        from django.utils import timezone
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])

    def mark_success(self, result=None):
        from django.utils import timezone
        self.status = 'success'
        self.progress = 100
        self.result = result
        self.completed_at = timezone.now()
        type(self).objects.filter(pk=self.pk, status__in=['pending', 'running']).update(
            status=self.status, progress=self.progress, result=self.result,
            completed_at=self.completed_at, updated_at=timezone.now())
        self.refresh_from_db()

    def mark_failed(self, error=''):
        from django.utils import timezone
        self.status = 'failed'
        self.error = error
        self.completed_at = timezone.now()
        type(self).objects.filter(pk=self.pk, status__in=['pending', 'running']).update(
            status=self.status, error=self.error, completed_at=self.completed_at, updated_at=timezone.now())
        self.refresh_from_db()

    def mark_cancelled(self):
        from django.utils import timezone
        self.status = 'cancelled'
        self.completed_at = timezone.now()
        changed = type(self).objects.filter(pk=self.pk, status__in=['pending', 'running']).update(
            status=self.status, completed_at=self.completed_at, updated_at=timezone.now())
        self.refresh_from_db()
        return bool(changed)


class MaintenanceRequest(models.Model):
    """已提交的维护请求；事务内登记，可靠事件触发执行。"""
    record = models.OneToOneField(TaskRecord, primary_key=True, on_delete=models.CASCADE, related_name='maintenance_request')
    key = models.CharField(max_length=40)
    options = models.JSONField(default=dict)
    session_version = models.PositiveIntegerField()
    request_id = models.CharField(max_length=100, blank=True)
    preview_id = models.UUIDField(null=True, blank=True)


class BackupRequest(models.Model):
    """宿主执行器领取凭证；不含数据库或远端存储凭据。"""
    record = models.OneToOneField(TaskRecord, primary_key=True, on_delete=models.CASCADE, related_name='backup_request')
    claim_token = models.UUIDField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    options = models.JSONField(default=dict)
