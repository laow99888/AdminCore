"""
认证应用模型
"""

from django.db import models
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
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '用户'
        verbose_name_plural = '用户'
        ordering = ['-date_joined']

    def __str__(self):
        return self.username
