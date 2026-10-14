"""
认证应用模型
"""

from django.db import models, transaction
from django.contrib.auth.models import AbstractUser
from apps.core.models import BaseModel
import uuid


class User(AbstractUser):
    """用户模型 - 继承 Django AbstractUser"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 额外字段
    avatar = models.URLField(blank=True, verbose_name='头像')
    phone = models.CharField(max_length=20, blank=True, verbose_name='电话')
    is_active = models.BooleanField(default=True, verbose_name='是否激活')
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

    @transaction.atomic
    def save(self, *args, **kwargs):
        # 所有 Model.save 写入口（本人资料、后台用户编辑及 Django admin）统一撤销旧归属。
        fields = kwargs.get('update_fields')
        email_changed = False
        if fields is None or 'email' in fields:
            self.email = self.email.strip().casefold()
            previous = type(self).objects.select_for_update().filter(pk=self.pk).values('email', 'verified_email').first()
            email_changed = previous is not None and previous['email'].strip().casefold() != self.email
            if email_changed or (self.verified_email and self.verified_email != self.email):
                self.verified_email = None
                if fields is not None:
                    kwargs['update_fields'] = set(fields) | {'verified_email'}
            elif previous is not None and fields is None:
                # 普通完整保存不得将旧对象中的归属覆盖回来；只有验证服务显式写该字段。
                self.verified_email = previous['verified_email']
        super().save(*args, **kwargs)
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
