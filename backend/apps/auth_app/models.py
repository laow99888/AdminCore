"""
认证应用模型
"""

from django.db import models, transaction
from django.contrib.auth.models import AbstractUser
from apps.core.models import BaseModel
from apps.core.fields import EncryptedPhoneField
import uuid


class User(AbstractUser):
    """用户模型 - 继承 Django AbstractUser"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 额外字段
    avatar = models.URLField(blank=True, verbose_name='头像')
    phone = EncryptedPhoneField(max_length=20, blank=True, verbose_name='电话')
    is_active = models.BooleanField(default=True, verbose_name='是否激活')
    is_service_account = models.BooleanField(default=False, editable=False, verbose_name='机器集成身份')
    last_login_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name='最后登录 IP')
    login_count = models.IntegerField(default=0, verbose_name='登录次数')
    session_version = models.PositiveIntegerField(default=0, verbose_name='登录凭据版本')
    must_change_password = models.BooleanField(default=False, verbose_name='下次登录必须修改密码')
    profile_version = models.PositiveIntegerField(default=1, verbose_name='个人资料版本')
    avatar_file = models.ForeignKey('files.FileModel', on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='avatar_users', verbose_name='托管头像')
    verified_email = models.EmailField(max_length=254, null=True, blank=True, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '用户'
        verbose_name_plural = '用户'
        ordering = ['-date_joined']
        indexes = [models.Index(fields=['created_at'])]

    def __str__(self):
        return self.username

    @property
    def email_verified(self):
        return bool(self.verified_email and self.verified_email == self.email.strip().casefold())

    def set_password(self, raw_password):
        if self.is_service_account and raw_password is not None:
            from django.core.exceptions import ValidationError
            raise ValidationError('机器身份不能设置登录密码')
        return super().set_password(raw_password)

    @transaction.atomic
    def save(self, *args, **kwargs):
        # 所有 Model.save 写入口（本人资料、后台用户编辑及 Django admin）统一撤销旧归属。
        fields = kwargs.get('update_fields')
        email_changed = False
        previous = type(self).objects.select_for_update().filter(pk=self.pk).values(
            'email', 'verified_email', 'is_active', 'session_version', 'is_service_account').first()
        from django.core.exceptions import ValidationError
        if previous and previous['is_service_account'] != self.is_service_account:
            raise ValidationError('普通用户和机器身份不能互相转换')
        if self.is_service_account and (self.has_usable_password() or self.is_staff or self.is_superuser
                                        or self.email or self.verified_email or self.phone):
            raise ValidationError('机器身份禁止交互密码、管理身份和个人联系方式')
        deactivated = bool(previous and previous['is_active'] and not self.is_active
                           and (fields is None or 'is_active' in fields))
        if previous and (fields is None or 'session_version' in fields or deactivated):
            # 旧 Model 实例不能把凭据版本写回较小值；禁用永久撤销此前凭据。
            self.session_version = max(self.session_version, previous['session_version'] + int(deactivated))
            if fields is not None:
                kwargs['update_fields'] = set(fields) | {'session_version'}
        if fields is None or 'email' in fields:
            self.email = self.email.strip().casefold()
            email_changed = previous is not None and previous['email'].strip().casefold() != self.email
            if email_changed or (self.verified_email and self.verified_email != self.email):
                self.verified_email = None
                if fields is not None:
                    kwargs['update_fields'] = set(kwargs['update_fields']) | {'verified_email'}
            elif previous is not None and fields is None:
                # 普通完整保存不得将旧对象中的归属覆盖回来；只有验证服务显式写该字段。
                self.verified_email = previous['verified_email']
        super().save(*args, **kwargs)
        if deactivated:
            from django.utils import timezone
            AuthSession.objects.filter(user=self, revoked_at__isnull=True).update(revoked_at=timezone.now())
        if email_changed:
            from django.utils import timezone
            EmailChallenge.objects.filter(user=self, consumed_at__isnull=True).update(consumed_at=timezone.now())


class AuthSession(models.Model):
    """服务器登记的 JWT 设备会话；客户端提示绝不参与身份判定。"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='jwt_sessions')
    session_version = models.PositiveIntegerField()
    password_hash = models.CharField(max_length=32)
    refresh_jti = models.CharField(max_length=255)
    created_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)

    class Meta:
        ordering = ['-last_seen_at', '-id']
        indexes = [models.Index(fields=['user', 'revoked_at', 'expires_at']),
                   models.Index(fields=['last_seen_at'])]


class EmailChallenge(models.Model):
    """只存快照和随机标识；邮件中的签名凭据由服务器临时派生。"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_challenges')
    purpose = models.CharField(max_length=20, choices=[('verify', '邮箱归属'), ('reset', '密码找回')])
    email = models.EmailField(max_length=254)
    session_version = models.PositiveIntegerField()
    password_digest = models.CharField(max_length=64)
    signing_key_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'purpose', 'consumed_at']), models.Index(fields=['expires_at'])]


class TOTPDevice(models.Model):
    """用户行先锁；密钥只保存独立 Fernet 密文，恢复码只保存散列。"""
    user = models.OneToOneField(User, primary_key=True, on_delete=models.CASCADE, related_name='totp_device')
    active_secret = models.TextField(blank=True)
    pending_secret = models.TextField(blank=True)
    pending_expires_at = models.DateTimeField(null=True, blank=True)
    pending_session_id = models.UUIDField(null=True, blank=True)
    pending_password_digest = models.CharField(max_length=64, blank=True)
    pending_session_version = models.PositiveIntegerField(null=True, blank=True)
    last_counter = models.BigIntegerField(default=-1)
    recovery_hashes = models.JSONField(default=list)


class LoginCaptchaGuard(models.Model):
    """SQL 共享的登录失败与挑战限频；身份只存摘要，不依赖 Redis。"""
    identity_digest = models.CharField(primary_key=True, max_length=64)
    failure_count = models.PositiveIntegerField(default=0)
    failure_expires_at = models.DateTimeField(null=True, blank=True)
    refresh_window = models.BigIntegerField(default=-1)
    refresh_count = models.PositiveIntegerField(default=0)
    current_challenge_id = models.UUIDField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)


class LoginCaptchaChallenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pair_digest = models.CharField(max_length=64)
    answer_digest = models.CharField(max_length=64)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
