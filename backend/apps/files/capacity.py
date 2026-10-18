"""持久化附件逻辑容量。回收站和文档历史仍占用，彻底删除后释放。

所有标准FileModel.save新增入口共用scope行锁与聚合复核。不计分片暂存、
Office派生、存储供应商实际计费，也不保证自定义bulk_create/SQL的额度。
"""
from contextlib import contextmanager

from django.db import transaction
from django.db.models import Sum

from apps.core.exceptions import APIError
from apps.core.tenancy import current_tenant_id, enabled


def capacity_scope():
    return current_tenant_id() if enabled() else None


def scope_key(owner_id, tenant_id):
    return f'{owner_id}:{tenant_id or "global"}'


def locked_capacity(owner_id, tenant_id):
    from .models import FileCapacity
    key = scope_key(owner_id, tenant_id)
    row, _ = FileCapacity.all_objects.get_or_create(scope_key=key, defaults={
        'owner_id': owner_id, 'tenant_id': tenant_id})
    return FileCapacity.all_objects.select_for_update().get(pk=row.pk)


def used_bytes(owner_id, tenant_id):
    from .models import FileModel
    return FileModel._base_manager.filter(uploader_id=owner_id, tenant_id=tenant_id).aggregate(
        total=Sum('size'))['total'] or 0


def capacity_data(owner_id, tenant_id, row=None):
    from .models import FileCapacity
    if row is None:
        row = FileCapacity.all_objects.filter(scope_key=scope_key(owner_id, tenant_id)).first()
    used = used_bytes(owner_id, tenant_id)
    limit = row.limit_bytes if row else 0
    return {'used_bytes': used, 'limit_bytes': limit, 'remaining_bytes': max(0, limit - used) if limit else None,
            'version': row.version if row else 0}


@contextmanager
def checked_file_creation(file):
    tenant_id = file.tenant_id or capacity_scope()
    with transaction.atomic():
        row = locked_capacity(file.uploader_id, tenant_id)
        if row.limit_bytes and used_bytes(file.uploader_id, tenant_id) + file.size > row.limit_bytes:
            raise APIError('文件容量配额不足，请清理回收站或联系管理员', status_code=409)
        yield
