"""
核心基础模型
"""

from django.db import models
import uuid


class BootstrapState(models.Model):
    """记录一次性种子数据已初始化，避免重启覆盖或恢复管理员删除的配置。"""
    key = models.CharField(max_length=100, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)


class BaseModel(models.Model):
    """所有模型的基类"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.__class__.__name__}({self.id})"


class SystemConfig(BaseModel):
    """只保存显式登记参数的覆盖值；部署密钥不进入此表。"""
    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField()
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey('auth_app.User', on_delete=models.SET_NULL, null=True)


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

    class Meta:
        ordering = ['order', 'name', 'id']


class OrganizationMembership(BaseModel):
    user = models.OneToOneField('auth_app.User', on_delete=models.CASCADE, related_name='organization_membership')
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='members')
    version = models.PositiveIntegerField(default=1)


class DataScopeGrant(BaseModel):
    RESOURCE_CHOICES = [(key, label) for key, label in [('user', '用户'), ('file', '文件'), ('task', '任务'), ('log', '日志')]]
    SCOPE_CHOICES = [(key, label) for key, label in [('self', '本人'), ('department', '本部门'),
                     ('department_tree', '部门及下级'), ('custom', '自定义部门'), ('all', '全部')]]
    role = models.ForeignKey('permissions.Role', on_delete=models.CASCADE, related_name='data_scope_grants')
    resource = models.CharField(max_length=20, choices=RESOURCE_CHOICES)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='self')
    departments = models.ManyToManyField(Department, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['role', 'resource'], name='unique_role_resource_scope')]
