"""文件级 ACL 与现有数据范围的合并策略。"""

from django.db.models import Exists, OuterRef, Q

from apps.core.data_scope import scope_queryset

from .models import FileModel, FileAccessGrant


def file_queryset_for_actor(queryset, actor, access=FileAccessGrant.READ, derivative=False):
    """返回租户内、数据范围内或被显式授权的文件。"""
    if not actor or not actor.is_authenticated:
        return queryset.none()
    if actor.is_staff or actor.is_superuser:
        return queryset
    scoped = scope_queryset(queryset, actor, 'file', 'uploader_id', fallback='self')
    grant_filter = {'file_id': OuterRef('pk'), 'is_active': True,
                    'access_level__in': [access, FileAccessGrant.MANAGE]}
    if derivative:
        grant_filter['inherit_to_derivatives'] = True
    grants = FileAccessGrant.objects.filter(**grant_filter).filter(
        Q(user=actor) | Q(role__userrole__user=actor, role__is_active=True))
    # 授权连接留在 EXISTS 子查询，外层一文件一行，可安全使用 PostgreSQL 行锁。
    return queryset.filter(Q(pk__in=scoped.values('pk')) | Exists(grants))


def file_can_access(file_obj, actor, access=FileAccessGrant.READ):
    return file_queryset_for_actor(
        FileModel.objects.filter(pk=file_obj.pk), actor, access=access
    ).exists()
