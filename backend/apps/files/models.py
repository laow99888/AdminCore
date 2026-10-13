"""
文件管理应用模型
"""

import os
import uuid

from django.db import models
from django.contrib.auth import get_user_model

from django.db import transaction
from apps.core.models import SoftDeleteModel, LifecycleConflict

User = get_user_model()


class FileStorageError(OSError):
    """向调用方提供不含存储地址、签名或凭据的失败信息。"""


def upload_to(instance, filename):
    """按日期分目录存储，使用 UUID 避免重名覆盖"""
    ext = os.path.splitext(filename)[1].lower()
    return f'uploads/{instance.created_at:%Y/%m/%d}/{uuid.uuid4().hex}{ext}'


class FileModel(SoftDeleteModel):
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

    class Meta:
        verbose_name = '文件'
        verbose_name_plural = '文件'
        indexes = [
            models.Index(fields=['uploader', 'is_deleted']),
            models.Index(fields=['file_type']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_deleted', 'deleted_at'], name='files_deleted_cutoff_idx'),
        ]

    def __str__(self):
        return self.original_name

    def validate_restore(self):
        try:
            exists = self.file and self.file.storage.exists(self.file.name)
        except Exception as exc:
            raise FileStorageError('存储暂时不可用，请稍后重试') from exc
        if not exists:
            raise LifecycleConflict('存储中的文件已不存在，无法恢复')

    def hard_delete(self, *, expected_version=None, deleted_before=None, audit=None):
        """行锁与恢复共用；清理任务持锁后复核状态和截止时间。存储失败保留记录。"""
        with transaction.atomic():
            row = type(self).objects.select_for_update().filter(pk=self.pk).first()
            if row is None:
                return False
            if expected_version is not None:
                row.check_lifecycle_version(expected_version)
            if deleted_before is not None and (
                not row.is_deleted or not row.deleted_at or row.deleted_at >= deleted_before
            ):
                return False
            if audit:
                audit(row)
            if row.file:
                try:
                    row.file.delete(save=False)
                except Exception as exc:
                    raise FileStorageError('存储暂时不可用，请稍后重试') from exc
            row.delete()
        return True
