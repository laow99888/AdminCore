"""
核心基础模型
"""

from django.db import models
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from .contracts import scope_resources
from .modules import MODULES
from .tenancy import current_tenant_id, enabled


class TenantManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_id = current_tenant_id() if enabled() else None
        if tenant_id is not None and any(field.name == 'tenant' for field in self.model._meta.get_fields()):
            queryset = queryset.filter(tenant_id=tenant_id)
        return queryset


class BootstrapState(models.Model):
    """记录一次性种子数据已初始化，避免重启覆盖或恢复管理员删除的配置。"""
    key = models.CharField(max_length=100, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Tenant(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_SUSPENDED = 'suspended'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [(STATUS_ACTIVE, '正常'), (STATUS_SUSPENDED, '暂停'), (STATUS_CLOSED, '已关闭')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'id']


class BaseModel(models.Model):
    """所有模型的基类"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey('core.Tenant', on_delete=models.PROTECT, null=True, blank=True,
                               related_name='%(app_label)s_%(class)s_records', verbose_name='租户')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        tenant_id = current_tenant_id() if enabled() else None
        if tenant_id is not None:
            if self.tenant_id is not None and str(self.tenant_id) != str(tenant_id):
                raise ValidationError('记录不能写入当前租户之外的租户')
            if self.tenant_id is None:
                self.tenant_id = tenant_id
                update_fields = kwargs.get('update_fields')
                if update_fields is not None and 'tenant' not in update_fields:
                    kwargs['update_fields'] = tuple(update_fields) + ('tenant',)
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.__class__.__name__}({self.id})"


class TenantMembership(models.Model):
    """用户在租户中的成员和管理角色。"""
    ROLE_CHOICES = [('owner', '所有者'), ('admin', '管理员'), ('member', '成员')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey('auth_app.User', on_delete=models.CASCADE, related_name='tenant_memberships')
    role = models.CharField(max_length=12, choices=ROLE_CHOICES, default='member')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = models.Manager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['tenant', 'user'], name='unique_tenant_membership')]
        indexes = [models.Index(fields=['user', 'is_active']), models.Index(fields=['tenant', 'is_active'])]


class LifecycleConflict(Exception):
    """状态、唯一字段或关联条件不允许本次生命周期操作。"""


class SoftDeleteModel(BaseModel):
    """可选择接入的软删除模型；查询可见性和关联恢复策略由资源明确实现。"""
    is_deleted = models.BooleanField(default=False, verbose_name='是否删除（软删除）')
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name='删除时间')
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='%(app_label)s_%(class)s_deleted', verbose_name='删除操作者',
    )
    lifecycle_version = models.PositiveIntegerField(default=1, verbose_name='生命周期版本')

    class Meta(BaseModel.Meta):
        abstract = True

    def check_lifecycle_version(self, expected_version):
        if expected_version != self.lifecycle_version:
            raise LifecycleConflict('记录已变化，请刷新后重试')

    def soft_delete(self, actor=None, expected_version=None):
        from django.db import transaction
        from django.utils import timezone
        with transaction.atomic():
            row = type(self)._base_manager.select_for_update().get(pk=self.pk)
            row.check_lifecycle_version(self.lifecycle_version if expected_version is None else expected_version)
            if not row.is_deleted:
                row.is_deleted = True
                row.deleted_at = timezone.now()
                row.deleted_by = actor
                row.lifecycle_version += 1
                row.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'lifecycle_version', 'updated_at'])
            self.__dict__.update(row.__dict__)
        return self

    def validate_restore(self):
        """扩展点：关联模型禁止自动复活；资源可在此检查其关联生命周期。"""
        pass

    def restore(self, expected_version):
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError, transaction
        try:
            with transaction.atomic():
                row = type(self)._base_manager.select_for_update().get(pk=self.pk)
                row.check_lifecycle_version(expected_version)
                if not row.is_deleted:
                    raise LifecycleConflict('记录已恢复，请刷新后重试')
                row.validate_restore()
                row.is_deleted = False
                # 包括以 is_deleted=False 为条件的唯一约束；不对历史记录补做字段格式校验。
                row.validate_unique()
                row.validate_constraints()
                row.deleted_at = None
                row.deleted_by = None
                row.lifecycle_version += 1
                row.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'lifecycle_version', 'updated_at'])
                self.__dict__.update(row.__dict__)
        except (ValidationError, IntegrityError) as exc:
            raise LifecycleConflict('恢复条件冲突，请检查唯一字段和关联记录') from exc
        return self


class SystemConfig(BaseModel):
    """只保存显式登记参数的覆盖值；部署密钥不进入此表。"""
    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField()
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey('auth_app.User', on_delete=models.SET_NULL, null=True)


class SavedListView(BaseModel):
    """查询方案不保存业务行或权限；每次读取、应用均按当前字段策略复核。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_list_views')
    module = models.CharField(max_length=64)
    name = models.CharField(max_length=80)
    shared = models.BooleanField(default=False)
    definition = models.JSONField()
    schema_digest = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [models.Index(fields=['tenant', 'module', 'owner'], name='saved_view_owner_scope')]


class DataDictionary(BaseModel):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    items = models.JSONField(default=list)
    version = models.PositiveIntegerField(default=1)


class Department(BaseModel):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='children')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    leader = models.ForeignKey('auth_app.User', on_delete=models.PROTECT, null=True, blank=True,
                               related_name='led_departments')

    class Meta:
        ordering = ['order', 'name', 'id']


class OrganizationMembership(BaseModel):
    user = models.OneToOneField('auth_app.User', on_delete=models.CASCADE, related_name='organization_membership')
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='members')
    version = models.PositiveIntegerField(default=1)


class OrganizationAppointment(BaseModel):
    """有界任期；与用于旧数据授权的 OrganizationMembership 分开维护。"""
    user = models.ForeignKey('auth_app.User', on_delete=models.PROTECT, related_name='organization_appointments')
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='appointments')
    kind = models.CharField(max_length=12, choices=[('primary', '主职'), ('secondary', '兼职')])
    starts_on = models.DateField()
    ends_on = models.DateField(null=True, blank=True)  # 左闭右开，允许同日无缝交接。
    cancelled = models.BooleanField(default=False)
    reason = models.CharField(max_length=500)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['-starts_on', 'id']
        constraints = [models.CheckConstraint(condition=models.Q(ends_on__isnull=True) | models.Q(ends_on__gt=models.F('starts_on')),
                                              name='appointment_valid_period')]
        indexes = [models.Index(fields=['tenant', 'user', 'kind', 'starts_on'], name='appointment_user_period')]


class Post(BaseModel):
    """任职信息，不参与角色授权或数据范围计算。"""
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=500, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['order', 'name', 'id']


class UserPost(BaseModel):
    user = models.ForeignKey('auth_app.User', on_delete=models.CASCADE, related_name='post_assignments')
    post = models.ForeignKey(Post, on_delete=models.PROTECT, related_name='assignments')
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'post'], name='unique_user_post')]


class DataScopeGrant(BaseModel):
    RESOURCE_CHOICES = scope_resources(MODULES)
    SCOPE_CHOICES = [(key, label) for key, label in [('self', '本人'), ('department', '本部门'),
                     ('department_tree', '部门及下级'), ('custom', '自定义部门'), ('all', '全部')]]
    role = models.ForeignKey('permissions.Role', on_delete=models.CASCADE, related_name='data_scope_grants')
    resource = models.CharField(max_length=20, choices=RESOURCE_CHOICES)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='self')
    departments = models.ManyToManyField(Department, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['role', 'resource'], name='unique_role_resource_scope')]


class IdempotencyRecord(BaseModel):
    """记录带 Idempotency-Key 的写请求，避免客户端重试产生重复副作用。"""
    STATUS_CHOICES = [('pending', '处理中'), ('succeeded', '已完成')]

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='idempotency_records')
    scope = models.CharField(max_length=120)
    key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_data = models.JSONField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['actor', 'scope', 'key'], name='unique_idempotency_actor_scope_key')]
        indexes = [models.Index(fields=['status', 'expires_at'])]
        ordering = ['-created_at']


class OutboxEvent(BaseModel):
    """事务内写入、事务外派发的可靠事件。"""
    STATUS_CHOICES = [('pending', '待派发'), ('processing', '派发中'), ('succeeded', '已完成'), ('failed', '失败')]

    topic = models.CharField(max_length=120)
    event_key = models.CharField(max_length=180, unique=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField()
    last_error = models.TextField(blank=True)
    request_id = models.CharField(max_length=100, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'available_at']), models.Index(fields=['topic', 'created_at'])]
        ordering = ['-created_at']


class RealtimeBudget(models.Model):
    """跨 ASGI worker 的连接准入锁；没有业务数据。"""
    key = models.PositiveSmallIntegerField(primary_key=True, default=1)


class RealtimeLease(models.Model):
    """每个设备会话最多一个连接；崩溃后的租约在 35 秒后不再占额度。"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField('auth_app.AuthSession', on_delete=models.CASCADE, related_name='realtime_lease')
    expires_at = models.DateTimeField(db_index=True)
