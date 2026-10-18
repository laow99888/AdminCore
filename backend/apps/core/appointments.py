"""任期与主管解析；审批使用当前有效主职，数据授权继续使用旧归属。"""
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Department, OrganizationAppointment, OrganizationMembership, TenantMembership
from .modules import module_enabled


def active_on(queryset, day):
    return queryset.filter(cancelled=False, starts_on__lte=day).filter(Q(ends_on__isnull=True) | Q(ends_on__gt=day))


def check_person(user, tenant_id):
    if user.is_service_account:
        raise ValidationError('机器身份不能任职或担任部门负责人')
    if not user.is_active:
        raise ValidationError('任职人员或部门负责人已停用')
    if tenant_id is not None and not TenantMembership.objects.filter(
            tenant_id=tenant_id, user_id=user.pk, is_active=True, tenant__status='active').exists():
        raise ValidationError('任职人员或部门负责人不是当前租户的有效成员')


def check_overlap(values, tenant_id):
    """调用者已锁定用户；同一用户的所有任期写入因此串行。"""
    rows = OrganizationAppointment.all_objects.filter(user=values['user'], tenant_id=tenant_id, cancelled=False)
    conflict = Q(department=values['department'])
    if values['kind'] == 'primary':
        conflict |= Q(kind='primary')
    rows = rows.filter(conflict)
    rows = rows.filter(Q(ends_on__isnull=True) | Q(ends_on__gt=values['starts_on']))
    if values.get('ends_on') is not None:
        rows = rows.filter(starts_on__lt=values['ends_on'])
    if rows.exists():
        raise ValidationError('任期重叠：主职只能有一项，同一部门的任职也不能重叠')


def department_leader(application, levels):
    if not module_enabled('organization'):
        raise ValidationError('部门主管审批需要启用组织模块')
    day = timezone.localdate()
    rows = OrganizationAppointment.all_objects.filter(user_id=application.applicant_id, tenant_id=application.tenant_id, kind='primary')
    current = list(active_on(rows, day).select_related('department')[:2])
    if len(current) > 1:
        raise ValidationError('申请人存在重叠主职任期，请管理员修正')
    appointment = current[0] if current else None
    if appointment:
        department = appointment.department
    elif rows.exists():
        # 一旦显式管理主职任期，过期、取消或未来任期不得回退到旧归属。
        raise ValidationError('申请人当前没有有效主职任职')
    else:
        membership = OrganizationMembership.all_objects.filter(user_id=application.applicant_id, tenant_id=application.tenant_id).select_related('department').first()
        department = membership.department if membership else None
    source_department = department
    visited = set()
    for index in range(levels):
        if not department or not department.is_active or department.tenant_id != application.tenant_id or department.pk in visited:
            raise ValidationError('主管链的部门不存在、已停用或形成循环')
        visited.add(department.pk)
        if index + 1 < levels:
            department = Department.all_objects.filter(pk=department.parent_id, tenant_id=application.tenant_id).select_related('leader').first()
    if not department.leader_id or department.leader_id == application.applicant_id:
        raise ValidationError('目标部门未设置负责人或负责人就是申请人，请调整流程')
    leader = department.leader
    check_person(leader, application.tenant_id)
    return leader, {'source': 'department_leader', 'levels': levels, 'resolved_on': day.isoformat(),
                    'appointment_id': str(appointment.pk) if appointment else None,
                    'source_department_id': str(source_department.pk), 'source_department_name': source_department.name,
                    'department_id': str(department.pk), 'department_name': department.name,
                    'assignee_id': str(leader.pk), 'assignee_name': leader.get_full_name() or leader.username}
