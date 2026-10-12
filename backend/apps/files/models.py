"""
文件管理应用模型
"""

import os
import uuid

from django.db import models
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel

User = get_user_model()


def upload_to(instance, filename):
    """按日期分目录存储，使用 UUID 避免重名覆盖"""
    ext = os.path.splitext(filename)[1].lower()
    return os.path.join('uploads', instance.created_at.strftime('%Y/%m/%d'), f'{uuid.uuid4().hex}{ext}')


class FileModel(BaseModel):
    """文件记录"""
    original_name = models.CharField(max_length=255, verbose_name='原始文件名')
    file = models.FileField(upload_to=upload_to, verbose_name='文件')
    file_type = models.CharField(max_length=20, verbose_name='文件类型（扩展名）')
    size = models.BigIntegerField(default=0, verbose_name='文件大小（字节）')
    content_type = models.CharField(max_length=100, blank=True, verbose_name='MIME 类型')
    md5 = models.CharField(max_length=32, blank=True, verbose_name='MD5 摘要')
    description = models.CharField(max_length=255, blank=True, verbose_name='描述')
    uploader = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='files', verbose_name='上传者')
    download_count = models.IntegerField(default=0, verbose_name='下载次数')
    is_deleted = models.BooleanField(default=False, verbose_name='是否删除（软删除）')
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name='删除时间')

    class Meta:
        verbose_name = '文件'
        verbose_name_plural = '文件'
        indexes = [
            models.Index(fields=['uploader', 'is_deleted']),
            models.Index(fields=['file_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.original_name

    def soft_delete(self):
        """软删除：标记状态并保留物理文件，等待清理任务处理"""
        from django.utils import timezone
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    def hard_delete(self):
        """物理删除：删除磁盘文件后删除记录"""
        if self.file:
            self.file.delete(save=False)
        self.delete()
