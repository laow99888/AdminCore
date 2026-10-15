import uuid
from django.conf import settings
from django.db import models


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

    class Meta:
        ordering = ('-created_at', '-id')
        indexes = [models.Index(fields=['owner', 'revoked_at'], name='api_cred_owner_revoked')]
