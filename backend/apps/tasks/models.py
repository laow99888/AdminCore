"""
任务调度应用模型
"""

import uuid

from django.db import models
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel, TenantManager

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
        changed = type(self).objects.filter(pk=self.pk, status='pending').update(
            status='running', started_at=timezone.now(), updated_at=timezone.now())
        self.refresh_from_db()
        return bool(changed)

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
        from django.db import transaction
        from django.utils import timezone
        with transaction.atomic():
            changed = type(self).objects.filter(pk=self.pk, status__in=['pending', 'running']).update(
                status='failed', error=error, completed_at=timezone.now(), updated_at=timezone.now())
            self.refresh_from_db()
            if changed:
                from .reliability import failure_event
                failure_event(self)
        return bool(changed)

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
    policy = models.JSONField(default=dict)
    session_id = models.UUIDField(null=True, blank=True)


class ImportBatch(BaseModel):
    """不可变源文件摘要和逐行提交账本；重试只接续未提交的行。"""
    source = models.ForeignKey('files.FileModel', on_delete=models.SET_NULL, null=True)
    source_sha256 = models.CharField(max_length=64)
    resource = models.CharField(max_length=100)
    active_record = models.ForeignKey(TaskRecord, on_delete=models.SET_NULL, null=True, related_name='+')


class ImportExecution(models.Model):
    tenant = models.ForeignKey('core.Tenant', on_delete=models.PROTECT, null=True, blank=True,
                               related_name='task_import_executions')
    record = models.OneToOneField(TaskRecord, on_delete=models.CASCADE, primary_key=True, related_name='import_execution')
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name='executions')
    attempt = models.PositiveSmallIntegerField(default=1)
    policy = models.JSONField(default=dict)
    session_version = models.PositiveIntegerField()
    session_id = models.UUIDField(null=True, blank=True)
    request_id = models.CharField(max_length=100, blank=True)
    objects = TenantManager()


class ImportRowReceipt(models.Model):
    tenant = models.ForeignKey('core.Tenant', on_delete=models.PROTECT, null=True, blank=True,
                               related_name='task_import_row_receipts')
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name='receipts')
    row = models.PositiveIntegerField()
    created = models.BooleanField()
    error = models.CharField(max_length=300, blank=True)
    objects = TenantManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['batch', 'row'], name='import_row_once')]


class BackupRequest(models.Model):
    """宿主执行器领取凭证；不含数据库或远端存储凭据。"""
    record = models.OneToOneField(TaskRecord, primary_key=True, on_delete=models.CASCADE, related_name='backup_request')
    claim_token = models.UUIDField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    options = models.JSONField(default=dict)


class BackupRunnerStatus(models.Model):
    """宿主执行器的受限心跳与已校验备份目录索引。"""
    key = models.PositiveSmallIntegerField(primary_key=True, default=1)
    state = models.CharField(max_length=20, default='offline')
    directory_label = models.CharField(max_length=200, blank=True)
    stage = models.CharField(max_length=40, blank=True)
    last_error = models.CharField(max_length=200, blank=True)
    artifacts = models.JSONField(default=list)
    restore_receipts = models.JSONField(default=list)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class BackupPreflight(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.CharField(max_length=15)
    actor = models.ForeignKey(User, on_delete=models.CASCADE)
    artifact_digest = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class BackupRestoreRequest(models.Model):
    """恢复请求只排队给宿主执行器；应用容器不执行 Docker 或数据库切换。"""
    STATUS_CHOICES = [('pending', '等待执行'), ('running', '执行中'), ('succeeded', '成功'),
                      ('failed', '失败'), ('unknown', '结果待核对')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.CharField(max_length=15)
    preflight_id = models.UUIDField(unique=True)
    session_version = models.PositiveIntegerField(default=0)
    session_id = models.UUIDField(null=True, blank=True)
    artifact_digest = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='backup_restore_requests')
    error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'created_at']), models.Index(fields=['timestamp', 'created_at'])]
        constraints = [models.UniqueConstraint(models.Value(1),
            condition=models.Q(status__in=['pending', 'running']), name='one_active_restore')]
