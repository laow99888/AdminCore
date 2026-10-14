"""
用户管理应用模型
"""

from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel
from apps.core.fields import EncryptedPhoneField

User = get_user_model()


class UserProfile(BaseModel):
    """用户资料"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', verbose_name='用户')
    bio = models.TextField(blank=True, verbose_name='个人简介')
    phone = EncryptedPhoneField(max_length=20, blank=True, verbose_name='电话')
    department = models.CharField(max_length=100, blank=True, verbose_name='部门')
    position = models.CharField(max_length=100, blank=True, verbose_name='职位')

    class Meta:
        verbose_name = '用户资料'
        verbose_name_plural = '用户资料'

    def __str__(self):
        return f"{self.user.username}'s Profile"
