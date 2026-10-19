"""个人映射和短期预检；源文件与业务数据分开保存。"""
from django.conf import settings
from django.db import models
from apps.core.models import BaseModel
from apps.files.fields import ScannedFileField


class ImportMapping(BaseModel):
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    resource = models.CharField(max_length=100)
    name = models.CharField(max_length=80)
    options = models.JSONField(default=dict)


class BusinessImportPlan(BaseModel):
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    resource = models.CharField(max_length=100)
    source = models.ForeignKey('files.FileModel', on_delete=models.SET_NULL, null=True)
    source_sha256 = models.CharField(max_length=64)
    options = models.JSONField(default=dict)
    summary = models.JSONField(default=dict)
    expires_at = models.DateTimeField(db_index=True)
    submitted_at = models.DateTimeField(null=True)
    record = models.ForeignKey('tasks.TaskRecord', on_delete=models.SET_NULL, null=True)


class BusinessExportRequest(BaseModel):
    """只经专属下载门禁访问的短期产物；快照不授予权限。"""
    id = None
    record = models.OneToOneField('tasks.TaskRecord', primary_key=True, on_delete=models.CASCADE,
                                  related_name='business_export_request')
    resource = models.CharField(max_length=100)
    options = models.JSONField(default=dict)
    snapshot = models.JSONField(default=list)
    policy = models.JSONField(default=dict)
    session_version = models.PositiveIntegerField()
    session_id = models.UUIDField(null=True, blank=True)
    request_id = models.CharField(max_length=100, blank=True)
    artifact = ScannedFileField(upload_to='private-business-exports/%Y/%m/%d/', blank=True)
    artifact_sha256 = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField(db_index=True)
