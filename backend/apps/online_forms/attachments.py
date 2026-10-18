"""在线表单附件：显式租户边界、当前 ACL、事务内锁定后绑定具体文件版本。"""
from apps.core.modules import module_enabled
from apps.files.access import file_queryset_for_actor
from apps.files.models import FileModel
from apps.permissions.permissions import has_permission_code
from rest_framework.exceptions import PermissionDenied, ValidationError
from uuid import UUID

from .models import OnlineFormFileReference


def file_values(definition, data, prefix=''):
    """只按冻结的字段类型解读值，文本中的 UUID 永远不会成为附件引用。"""
    for field in definition.get('fields', []):
        key = field['key']
        value = data.get(key)
        path = prefix + key
        if field['type'] == 'file' and value:
            yield path, value
        elif field['type'] == 'detail' and isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    yield from file_values(field, item, f'{path}.{index}.')


def readable_files(actor, tenant_id):
    if not module_enabled('files') or not has_permission_code(actor, 'file:read'):
        raise PermissionDenied('没有附件读取权限')
    # TenantManager 在平台管理员未选租户时不做过滤；此处仍必须匹配表单的显式租户。
    return file_queryset_for_actor(FileModel.objects.filter(
        tenant_id=tenant_id, is_deleted=False, purpose='general'), actor)


def validate_files(definition, data, actor, tenant_id, *, lock=False):
    values = dict(file_values(definition, data))
    if not values:
        return values
    identifiers = set(values.values())
    if lock:
        # 与 files.references 约定一致：先锁文件，再复核 ACL/状态/租户，最后同事务附 PROTECT 引用。
        list(FileModel._base_manager.select_for_update().filter(
            tenant_id=tenant_id, pk__in=identifiers).order_by('pk'))
    allowed = {str(pk) for pk in readable_files(actor, tenant_id).filter(pk__in=identifiers).values_list('pk', flat=True)}
    errors = {path: '附件不可用或不在授权范围内' for path, identifier in values.items() if identifier not in allowed}
    if errors:
        raise ValidationError(errors)
    return values


def attach_files(record, values):
    existing = set(record.file_references.values_list('file_id', flat=True))
    unique = {}
    for path, identifier in values.items():
        unique.setdefault(identifier, path)
    OnlineFormFileReference.objects.bulk_create([
        OnlineFormFileReference(record=record, file_id=identifier,
            first_record_version=record.version, first_field_path=path, tenant_id=record.tenant_id)
        for identifier, path in unique.items() if UUID(identifier) not in existing
    ])


def public_file(row):
    # 不返回存储 URL、签名、文件内容或关联业务字段。
    return {'id': str(row.pk), 'original_name': row.original_name, 'file_type': row.file_type, 'size': row.size}
