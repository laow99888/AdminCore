"""私有临时转换产物；不注册成一般文件，不暴露存储位置或领取令牌。"""
from django.conf import settings
from django.db import models
from apps.core.models import BaseModel


class OfficePreview(BaseModel):
    # History deletion must not orphan private storage objects before TTL cleanup.
    record = models.OneToOneField('tasks.TaskRecord', on_delete=models.SET_NULL, null=True, related_name='office_preview')
    source = models.ForeignKey('files.FileModel', on_delete=models.SET_NULL, null=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    session = models.ForeignKey('auth_app.AuthSession', on_delete=models.SET_NULL, null=True)
    session_version = models.PositiveIntegerField()
    source_version = models.PositiveIntegerField()
    source_sha256 = models.CharField(max_length=64)
    engine = models.CharField(max_length=255)
    claim_digest = models.CharField(max_length=64, blank=True)
    claimed_at = models.DateTimeField(null=True)
    expires_at = models.DateTimeField(db_index=True)
    output_key = models.CharField(max_length=255, blank=True)
    output_sha256 = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [models.Index(fields=['actor', 'created_at'], name='office_actor_created_idx')]
