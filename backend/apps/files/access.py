"""文件级 ACL 与现有数据范围的合并策略。"""

from django.db.models import Q

from apps.core.data_scope import scope_queryset

from .models import FileModel, FileAccessGrant


def file_queryset_for_actor(queryset, actor, access=FileAccessGrant.READ, derivative=False):
    """返回租户内、数据范围内或被显式授权的文件。"""
    if not actor or not actor.is_authenticated:
        return queryset.none()
    if actor.is_staff or actor.is_superuser:
        return queryset
    scoped = scope_queryset(queryset, actor, 'file', 'uploader_id', fallback='self')
    grant_filter = {'access_grants__is_active': True,
                    'access_grants__access_level__in': [access, FileAccessGrant.MANAGE]}
    if derivative:
        grant_filter['access_grants__inherit_to_derivatives'] = True
    principal = (Q(access_grants__user=actor, **grant_filter)
                 | Q(access_grants__role__userrole__user=actor,
                     access_grants__role__is_active=True, **grant_filter))
    return queryset.filter(Q(pk__in=scoped.values('pk')) | principal).distinct()


def file_can_access(file_obj, actor, access=FileAccessGrant.READ):
    return file_queryset_for_actor(
        FileModel.objects.filter(pk=file_obj.pk), actor, access=access
    ).exists()
