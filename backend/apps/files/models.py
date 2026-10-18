"""
文件管理应用模型
"""

import os
import uuid

from django.db import models
from django.contrib.auth import get_user_model

from django.db import transaction
from apps.core.models import BaseModel, SoftDeleteModel, LifecycleConflict
from .fields import ScannedFileField

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
    file = ScannedFileField(upload_to=upload_to, verbose_name='文件')
    file_type = models.CharField(max_length=20, verbose_name='文件类型（扩展名）')
    size = models.BigIntegerField(default=0, verbose_name='文件大小（字节）')
    content_type = models.CharField(max_length=100, blank=True, verbose_name='MIME 类型')
    md5 = models.CharField(max_length=32, blank=True, verbose_name='MD5 摘要')
    description = models.CharField(max_length=255, blank=True, verbose_name='描述')
    uploader = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='files', verbose_name='上传者')
    download_count = models.IntegerField(default=0, verbose_name='下载次数')
    purpose = models.CharField(max_length=16, default='general', choices=[('general', '普通文件'), ('avatar', '个人头像'), ('import', '导入源文件')])

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

    def save(self, *args, **kwargs):
        if self._state.adding and self.uploader_id:
            from .capacity import checked_file_creation
            with checked_file_creation(self):
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def soft_delete(self, actor=None, expected_version=None):
        from .references import assert_not_referenced
        with transaction.atomic():
            row = type(self)._base_manager.select_for_update().get(pk=self.pk)
            row.check_lifecycle_version(self.lifecycle_version if expected_version is None else expected_version)
            assert_not_referenced(row)
            row = super(FileModel, row).soft_delete(actor=actor, expected_version=row.lifecycle_version)
            self.__dict__.update(row.__dict__)
        return self

    def validate_restore(self):
        if self.purpose == 'avatar':
            raise LifecycleConflict('历史头像不能从文件回收站恢复，请重新上传')
        try:
            exists = self.file and self.file.storage.exists(self.file.name)
        except Exception as exc:
            raise FileStorageError('存储暂时不可用，请稍后重试') from exc
        if not exists:
            raise LifecycleConflict('存储中的文件已不存在，无法恢复')

    def hard_delete(self, *, expected_version=None, deleted_before=None, audit=None):
        """原子登记存储删除意图并删除记录；提交前绝不删除存储对象。"""
        with transaction.atomic():
            row = type(self).objects.select_for_update().filter(pk=self.pk).first()
            if row is None:
                return False
            if row.avatar_users.exists():
                raise LifecycleConflict('当前头像仍被用户引用，不能彻底删除')
            if expected_version is not None:
                row.check_lifecycle_version(expected_version)
            if deleted_before is not None and (
                not row.is_deleted or not row.deleted_at or row.deleted_at >= deleted_before
            ):
                return False
            from .references import assert_not_referenced
            assert_not_referenced(row)
            if audit:
                audit(row)
            if row.file:
                from apps.core.events import enqueue_event
                from .deletion import storage_identity
                enqueue_event('file.purge', 'file-purge:' + str(row.pk),
                              {'name': row.file.name, 'storage': storage_identity()})
            row.delete()
        return True


class FileAccessGrant(BaseModel):
    """文件的显式访问授权；用户和角色只能二选一。"""
    READ = 'read'
    MANAGE = 'manage'
    ACCESS_CHOICES = [(READ, '读取'), (MANAGE, '管理')]

    file = models.ForeignKey(FileModel, on_delete=models.CASCADE, related_name='access_grants')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True,
                             related_name='file_access_grants')
    role = models.ForeignKey('permissions.Role', on_delete=models.CASCADE, null=True, blank=True,
                             related_name='file_access_grants')
    access_level = models.CharField(max_length=8, choices=ACCESS_CHOICES, default=READ)
    inherit_to_derivatives = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(user__isnull=False, role__isnull=True)
                           | models.Q(user__isnull=True, role__isnull=False)),
                name='file_grant_one_principal',
            ),
            models.UniqueConstraint(fields=['file', 'user'], name='file_grant_unique_user'),
            models.UniqueConstraint(fields=['file', 'role'], name='file_grant_unique_role'),
        ]
        indexes = [
            models.Index(fields=['file', 'access_level', 'is_active']),
            models.Index(fields=['user', 'access_level', 'is_active']),
            models.Index(fields=['role', 'access_level', 'is_active']),
        ]


class ResumableUpload(BaseModel):
    """可恢复分片上传会话；分片对象本身存储在默认媒体存储中。"""
    STATUS_CHOICES = [('active', '进行中'), ('completed', '已完成'), ('expired', '已过期')]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='resumable_uploads')
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    total_size = models.PositiveBigIntegerField()
    chunk_size = models.PositiveIntegerField()
    total_chunks = models.PositiveIntegerField()
    expected_sha256 = models.CharField(max_length=64, blank=True)
    chunks = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='active', db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    file = models.OneToOneField(FileModel, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='resumable_upload')

    class Meta:
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['status', 'expires_at']),
        ]


class FileFolder(BaseModel):
    """个人目录仅整理文件，不参与文件 ACL 或数据范围计算。"""
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='file_folders')
    parent = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True,
                               related_name='children')
    name = models.CharField(max_length=80)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [models.Index(fields=['owner', 'tenant'])]


class FileOrganization(BaseModel):
    file = models.ForeignKey(FileModel, on_delete=models.CASCADE, related_name='organizations')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='file_organizations')
    folder = models.ForeignKey(FileFolder, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='organizations')
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['file', 'owner'], name='unique_file_organization_owner')]
        indexes = [models.Index(fields=['owner', 'tenant', 'folder'])]


class FileOrganizationTag(BaseModel):
    organization = models.ForeignKey(FileOrganization, on_delete=models.CASCADE, related_name='tags')
    name = models.CharField(max_length=32)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['organization', 'name'], name='unique_file_organization_tag')]
        indexes = [models.Index(fields=['name', 'organization'])]


class FileDocument(BaseModel):
    """逻辑文档不授予文件权限；每个修订保留自己的不可变附件。"""
    current_file = models.ForeignKey(FileModel, on_delete=models.PROTECT, related_name='current_documents')
    version = models.PositiveIntegerField(default=1)


class FileRevision(BaseModel):
    document = models.ForeignKey(FileDocument, on_delete=models.CASCADE, related_name='revisions')
    file = models.ForeignKey(FileModel, on_delete=models.PROTECT, related_name='document_revisions')
    number = models.PositiveIntegerField()
    restored_from = models.PositiveIntegerField(null=True, blank=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['document', 'number'], name='unique_file_document_revision')]


class FileCapacity(BaseModel):
    # 固定scope键也隔离NULL全局租户；避免依赖数据库对NULL唯一值的不同处理。
    scope_key = models.CharField(max_length=80, unique=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='file_capacities')
    limit_bytes = models.PositiveBigIntegerField(default=0)
    version = models.PositiveIntegerField(default=0)


from .office_models import OfficePreview  # noqa: E402,F401
