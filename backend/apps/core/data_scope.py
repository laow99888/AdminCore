"""对象权限统一入口：未配置资源范围时保留原行为，配置后按有效角色合并范围。"""
from django.db.models import Q
from .models import Department, OrganizationMembership, DataScopeGrant


def grants_for(user, resource):
    # 授权属于安全核心；关闭组织管理界面不能撤掉既有范围限制。
    return list(DataScopeGrant.objects.filter(resource=resource, role__userrole__user=user)
                .select_related('role').prefetch_related('departments'))


def descendant_ids(identifier):
    children = {}
    for pk, parent in Department.objects.filter(is_active=True).values_list('pk', 'parent_id'):
        children.setdefault(parent, []).append(pk)
    result, queue = set(), [identifier]
    while queue:
        current = queue.pop()
        if current in result:
            continue
        result.add(current)
        queue.extend(children.get(current, []))
    return result


def scope_queryset(queryset, user, resource, owner_field, fallback='all'):
    if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
        return queryset
    if not getattr(user, 'is_authenticated', False):
        return queryset.none()
    grants = grants_for(user, resource)
    if not grants:
        return queryset.filter(**{owner_field: user.pk}) if fallback == 'self' else queryset
    # 已配置范围的角色停用后不能退回“未配置”的宽范围兼容规则。
    grants = [grant for grant in grants if grant.role.is_active]
    if any(grant.scope == 'all' for grant in grants):
        return queryset
    allowed = Q(pk__in=[])
    departments = set()
    own_department = (OrganizationMembership.objects.filter(user=user, department__is_active=True).values_list('department_id', flat=True).first()
                      if any(grant.scope in ('department', 'department_tree') for grant in grants) else None)
    for grant in grants:
        if grant.scope == 'self':
            allowed |= Q(**{owner_field: user.pk})
        elif grant.scope == 'custom':
            departments.update(department.pk for department in grant.departments.all() if department.is_active)
        elif own_department and grant.scope == 'department':
            departments.add(own_department)
        elif own_department and grant.scope == 'department_tree':
            departments.update(descendant_ids(own_department))
    if departments:
        users = OrganizationMembership.objects.filter(department_id__in=departments).values('user_id')
        allowed |= Q(**{owner_field + '__in': users})
    return queryset.filter(allowed)


def unrestricted_user_creation(user):
    if user.is_staff or user.is_superuser:
        return True
    grants = grants_for(user, 'user')
    return not grants or any(grant.role.is_active and grant.scope == 'all' for grant in grants)
