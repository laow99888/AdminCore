import uuid

from django.conf import settings
from django.db import models


class ExternalIdentity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    issuer = models.CharField(max_length=512)
    subject = models.CharField(max_length=255)
    binding_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['issuer', 'subject'], name='sso_unique_issuer_subject'),
                       models.UniqueConstraint(fields=['issuer', 'user'], name='sso_unique_issuer_user')]
        ordering = ['-created_at', 'pk']


class LoginFlow(models.Model):
    """No codes, IdP tokens or local JWTs are stored. Verifiers are encrypted and erased on consume."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    state_digest = models.CharField(max_length=64, unique=True)
    browser_digest = models.CharField(max_length=64)
    nonce_digest = models.CharField(max_length=64)
    encrypted_verifier = models.TextField()
    config_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True)
    identity = models.ForeignKey(ExternalIdentity, on_delete=models.CASCADE, null=True)
    binding_version = models.PositiveIntegerField(null=True)
    password_digest = models.CharField(max_length=64, blank=True)
    session_version = models.PositiveIntegerField(null=True)
    completion_digest = models.CharField(max_length=64, blank=True)
    completed_at = models.DateTimeField(null=True)


class SSOSession(models.Model):
    session = models.OneToOneField('auth_app.AuthSession', primary_key=True, on_delete=models.CASCADE)
    identity = models.ForeignKey(ExternalIdentity, on_delete=models.CASCADE)
    binding_version = models.PositiveIntegerField()
    config_digest = models.CharField(max_length=64)
