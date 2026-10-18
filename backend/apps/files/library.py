"""个人文件整理；文件读取授权始终由 access 模块独立决定。"""
from uuid import UUID

from django.db.models import Exists, OuterRef, Prefetch
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.exceptions import APIError
from apps.core.tenancy import current_tenant_id, enabled
from .access import file_queryset_for_actor
from .models import FileFolder, FileModel, FileOrganization

MAX_FOLDERS = 200
MAX_DEPTH = 8


def personal_rows(model, actor):
    # 平台管理员未选租户时也只能编辑全局个人整理，不能串读各租户目录。
    return model.objects.filter(owner=actor, tenant_id=current_tenant_id() if enabled() else None)


def visible_files(actor):
    return file_queryset_for_actor(FileModel.objects.filter(purpose='general', is_deleted=False), actor)


def with_organization(queryset, actor):
    return queryset.prefetch_related(Prefetch('organizations',
        queryset=personal_rows(FileOrganization, actor).prefetch_related('tags'), to_attr='personal_organization'))


def organization_data(row):
    return {'version': row.version, 'folder': str(row.folder_id) if row.folder_id else None,
            'tags': sorted(item.name for item in row.tags.all())} if row else {'version': 0, 'folder': None, 'tags': []}


def filter_folder(queryset, actor, value):
    placements = personal_rows(FileOrganization, actor).filter(file_id=OuterRef('pk'))
    if value == 'unfiled':
        return queryset.filter(~Exists(placements.filter(folder__isnull=False)))
    try:
        identifier = UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({'folder': '目录标识无效'}) from None
    if not personal_rows(FileFolder, actor).filter(pk=identifier).exists():
        raise NotFound('目录不存在')
    return queryset.filter(Exists(placements.filter(folder_id=identifier)))


def folder_for(actor, identifier):
    if identifier is None:
        return None
    row = personal_rows(FileFolder, actor).filter(pk=identifier).first()
    if row is None:
        raise NotFound('目录不存在')
    return row


def validate_folder(actor, name, parent, row=None):
    folders = list(personal_rows(FileFolder, actor))
    if row is None and len(folders) >= MAX_FOLDERS:
        raise ValidationError({'folder': '个人目录最多200个'})
    if any(item.name.casefold() == name.casefold() and item.parent_id == (parent.pk if parent else None)
           and (row is None or item.pk != row.pk) for item in folders):
        raise APIError('同级目录名称已存在', status_code=409)
    parents = {item.pk: item.parent_id for item in folders}
    if row:
        parents[row.pk] = parent.pk if parent else None
    else:
        parents[UUID(int=0)] = parent.pk if parent else None
    # 检查整棵树，也覆盖移动父目录导致已有后代超过深度上限的情况。
    for identifier in parents:
        seen = set()
        while identifier is not None:
            if identifier in seen:
                raise ValidationError({'parent': '目录不能移动到自身或子目录下'})
            seen.add(identifier)
            if len(seen) > MAX_DEPTH:
                raise ValidationError({'parent': '目录最多8级'})
            identifier = parents.get(identifier)


def check_version(row, expected):
    if (row.version if row else 0) != expected:
        raise APIError('整理信息已变更，请刷新后重试', status_code=409)
