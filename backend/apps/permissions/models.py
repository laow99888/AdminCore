"""
权限系统模型 - RBAC
"""

from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel

User = get_user_model()


class Role(BaseModel):
    """角色模型"""
    name = models.CharField(max_length=100, unique=True, verbose_name='角色名')
    description = models.TextField(blank=True, verbose_name='描述')
    is_active = models.BooleanField(default=True, verbose_name='是否激活')
    version = models.PositiveIntegerField(default=1)
    field_permissions = models.JSONField(default=dict, blank=True, verbose_name='字段权限策略')

    class Meta:
        verbose_name = '角色'
        verbose_name_plural = '角色'

    def __str__(self):
        return self.name


class Permission(BaseModel):
    """权限模型"""
    name = models.CharField(max_length=100, unique=True, verbose_name='权限名')
    code = models.CharField(max_length=100, unique=True, verbose_name='权限代码')
    description = models.TextField(blank=True, verbose_name='描述')
    resource = models.CharField(max_length=100, verbose_name='资源')  # 如 'user', 'role' 等
    action = models.CharField(max_length=100, verbose_name='操作')  # 如 'create', 'read', 'update', 'delete'

    class Meta:
        verbose_name = '权限'
        verbose_name_plural = '权限'
        unique_together = ('resource', 'action')

    def __str__(self):
        return f"{self.resource}:{self.action}"


class RolePermission(BaseModel):
    """角色权限关联"""
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='permissions', verbose_name='角色')
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, verbose_name='权限')

    class Meta:
        verbose_name = '角色权限'
        verbose_name_plural = '角色权限'
        unique_together = ('role', 'permission')

    def __str__(self):
        return f"{self.role.name} - {self.permission.code}"


class UserRole(BaseModel):
    """用户角色关联"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='roles', verbose_name='用户')
    role = models.ForeignKey(Role, on_delete=models.CASCADE, verbose_name='角色')

    class Meta:
        verbose_name = '用户角色'
        verbose_name_plural = '用户角色'
        unique_together = ('user', 'role')

    def __str__(self):
        return f"{self.user.username} - {self.role.name}"


class Menu(BaseModel):
    """菜单模型"""
    name = models.CharField(max_length=100, verbose_name='菜单名')
    path = models.CharField(max_length=200, unique=True, verbose_name='路由路径')
    icon = models.CharField(max_length=100, blank=True, verbose_name='图标')
    order = models.IntegerField(default=0, verbose_name='排序')
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='父菜单'
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='所需权限'
    )
    is_visible = models.BooleanField(default=True, verbose_name='是否可见')
    version = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = '菜单'
        verbose_name_plural = '菜单'
        # 注意：parent 是自引用外键，不能出现在默认排序里，
        # 否则 Django 解析排序时递归回自身默认排序，抛
        # FieldError: Infinite loop caused by ordering
        ordering = ['order']

    def __str__(self):
        return self.name
