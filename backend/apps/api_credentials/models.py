import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class ServiceIdentity(models.Model):
    """固定归属的非交互主体；授权复用其独立 User 的角色和数据范围。"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, primary_key=True, on_delete=models.CASCADE,
                               related_name='service_identity')
    tenant = models.ForeignKey('core.Tenant', null=True, on_delete=models.PROTECT)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                   related_name='created_service_identities')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', 'user_id')


class APICredential(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    secret_digest = models.CharField(max_length=64, editable=False)
    password_digest = models.CharField(max_length=64, editable=False)
    session_version = models.PositiveIntegerField(editable=False)
    scopes = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    usage_window = models.BigIntegerField(default=-1, editable=False)
    usage_count = models.PositiveIntegerField(default=0, editable=False)
    version = models.PositiveIntegerField(default=1, editable=False)
    rotated_at = models.DateTimeField(null=True, editable=False)
    accepted_requests = models.PositiveBigIntegerField(default=0, editable=False)
    statistics_started_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ('-created_at', '-id')
        indexes = [models.Index(fields=['owner', 'revoked_at'], name='api_cred_owner_revoked')]


class CredentialUsageDay(models.Model):
    """仅计通过认证和能力校验的请求，不记录令牌、查询或业务载荷。"""
    credential = models.ForeignKey(APICredential, on_delete=models.CASCADE, related_name='daily_usage')
    day = models.DateField()
    requests = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['credential', 'day'], name='api_cred_usage_day_unique')]
