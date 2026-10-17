"""跨模块 HTTP 对象矩阵：本租户可读，其他租户同一所有者的 ID 也不可读写。"""
import pytest
from django.forms.models import model_to_dict
from rest_framework.test import APIClient
from rest_framework.viewsets import GenericViewSet

from apps.approvals.models import ApprovalFlow, ApprovalRequest
from apps.core.models import Department, Tenant, TenantMembership
from apps.core.tenancy import tenant_context
from apps.core.query_budget import QueryBudgetListMixin
from apps.example.models import WorkItem
from apps.files.models import FileModel
from apps.feature_flags.models import FeatureFlag
from apps.notifications.models import Notification
from apps.online_forms.models import OnlineForm
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.reports.models import ReportDefinition
from apps.tasks.models import TaskRecord

pytestmark = pytest.mark.django_db

CASES = [
    ('task', '/api/v1/tasks/', 'post', 'cancel/', {}),
    ('example', '/api/v1/example/items/', 'patch', '', {'title': '越界修改', 'version': 1}),
    ('notification', '/api/v1/notifications/', 'post', 'mark_read/', {}),
    ('approval', '/api/v1/approvals/', 'post', 'cancel/', {}),
    ('form', '/api/v1/online-forms/forms/', 'post', 'archive/', {}),
    ('report', '/api/v1/reports/definitions/', 'post', 'archive/', {}),
    ('file', '/api/v1/files/', 'get', 'download/', None),
    ('flow', '/api/v1/approvals/flows/', 'post', 'archive/', {}),
    ('flow', '/api/v1/approvals/flows/', 'post', 'publish/', {}),
    ('department', '/api/v1/organization/departments/', 'patch', '', {'name': '越界修改', 'version': 1}),
    ('feature_flag', '/api/v1/feature-flags/flags/', 'patch', '', {'name': '越界修改', 'version': 1}),
]


def create_row(kind, user, label):
    if kind == 'task':
        return TaskRecord.objects.create(name=label, creator=user)
    if kind == 'example':
        return WorkItem.objects.create(title=label, creator=user)
    if kind == 'notification':
        return Notification.objects.create(title=label, recipient=user)
    if kind == 'approval':
        return ApprovalRequest.objects.create(title=label, applicant=user, assignee=user, content=label)
    if kind == 'form':
        return OnlineForm.objects.create(name=label, code=label, created_by=user)
    if kind == 'report':
        return ReportDefinition.objects.create(name=label, code=label, created_by=user)
    if kind == 'flow':
        from tests.test_advanced_approvals import definition
        return ApprovalFlow.objects.create(name=label, code=label, created_by=user, definition=definition(user))
    if kind == 'department':
        return Department.objects.create(name=label)
    if kind == 'feature_flag':
        return FeatureFlag.objects.create(name=label, key=label)
    return FileModel.objects.create(original_name=label + '.txt', file_type='txt', uploader=user)


@pytest.mark.parametrize('actor_kind,kind,base,method,action,payload', [
    (actor_kind, *case) for case in CASES for actor_kind in ('admin', 'member')
    if actor_kind == 'admin' or case[0] not in {'flow', 'department', 'feature_flag'}
])
def test_tenant_header_bounds_lists_direct_ids_and_actions(settings, admin_user, member_user, actor_kind,
                                                          kind, base, method, action, payload):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    settings.ROOT_URLCONF = 'tests.tenant_object_urls'
    settings.ADMINCORE_MODULES = ('tasks', 'example', 'notifications', 'approvals', 'online_forms', 'reports',
                                 'files', 'organization', 'feature_flags')
    first = Tenant.objects.create(slug='first', name='本租户')
    second = Tenant.objects.create(slug='second', name='其它租户')
    actor = admin_user if actor_kind == 'admin' else member_user
    # 同一个用户拥有两边数据，不能把所有者/管理员权限误当成跨租户通行证。
    with tenant_context(first.pk):
        if actor_kind == 'member':
            TenantMembership.objects.create(tenant=first, user=actor)
            role = Role.objects.create(name='本租户业务权限')
            UserRole.objects.create(user=actor, role=role)
            for code in ['task:read', 'task:cancel', 'example:read', 'example:update', 'file:read',
                         'file:download', 'online_form:read', 'online_form:update', 'report:read', 'report:update']:
                resource, action_code = code.split(':')
                permission = Permission.objects.create(code=code, name=code, resource=resource, action=action_code)
                RolePermission.objects.create(role=role, permission=permission)
        own = create_row(kind, actor, 'own')
        if kind == 'report' and actor_kind == 'member':
            own.status = 'published'
            own.save(update_fields=['status'])
    with tenant_context(second.pk):
        foreign = create_row(kind, actor, 'foreign')
        if kind == 'report' and actor_kind == 'member':
            foreign.status = 'published'
            foreign.save(update_fields=['status'])
    before = model_to_dict(type(foreign).all_objects.get(pk=foreign.pk))
    client = APIClient()
    client.force_authenticate(actor)
    headers = {'HTTP_X_ADMINCORE_TENANT': str(first.pk)}
    listed = client.get(base, **headers)
    assert listed.status_code == 200, listed.data
    assert {item['id'] for item in listed.data['data']['items']} == {str(own.pk)}
    assert client.get(f'{base}{own.pk}/', **headers).status_code == 200
    assert client.get(f'{base}{foreign.pk}/', **headers).status_code == 404
    arguments = {'data': payload, 'format': 'json'} if method != 'get' else {}
    denied = getattr(client, method)(f'{base}{foreign.pk}/{action}', **arguments, **headers)
    assert denied.status_code == 404, denied.data
    # 独立未过滤管理器只供断言，确认错误请求没改变外租户行或软删除/下载计数。
    saved = type(foreign).all_objects.get(pk=foreign.pk)
    assert model_to_dict(saved) == before
    if kind == 'flow':
        allowed = client.post(f'{base}{own.pk}/{action}', format='json', **headers)
        assert allowed.status_code == 200, allowed.data
        own.refresh_from_db()
        assert own.status == ('published' if action == 'publish/' else 'archived')


def test_class_queryset_is_restricted_per_request_without_changing_disabled_or_control_plane(settings, admin_user):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    first = Tenant.objects.create(slug='first', name='第一租户')
    second = Tenant.objects.create(slug='second', name='第二租户')
    rows = []
    for tenant in (first, second):
        with tenant_context(tenant.pk):
            rows.append(WorkItem.objects.create(title=tenant.name, creator=admin_user))
        TenantMembership.objects.create(tenant=tenant, user=admin_user)

    # 类定义发生在任何请求租户之外，模拟真实模块导入并保留既有 select_related。
    class BusinessView(QueryBudgetListMixin, GenericViewSet):
        queryset = WorkItem.objects.select_related('creator')

    class ControlPlaneView(QueryBudgetListMixin, GenericViewSet):
        queryset = TenantMembership.objects.all()

    view = BusinessView()
    for index, tenant in enumerate((first, second)):
        with tenant_context(tenant.pk):
            assert list(view.get_queryset().values_list('pk', flat=True)) == [rows[index].pk]
            assert view.get_queryset().query.select_related == {'creator': {}}
            # 租户成员关系是全局控制面，不继承业务 BaseModel 的 tenant 限定。
            assert ControlPlaneView().get_queryset().count() == 2
    assert view.get_queryset().count() == 2
    settings.ADMINCORE_MULTI_TENANT_ENABLED = False
    with tenant_context(first.pk):
        assert view.get_queryset().count() == 2


@pytest.mark.parametrize('serializer_path,field,kind,many', [
    ('apps.approvals.serializers.ApprovalCreateSerializer', 'flow_id', 'flow', False),
    ('apps.core.organization_serializers.ScopeGrantSerializer', 'departments', 'department', True),
    ('apps.users.serializers.UserCreateSerializer', 'role_ids', 'role', True),
    ('apps.users.serializers.UserUpdateSerializer', 'role_ids', 'role', True),
    ('apps.permissions.serializers.RoleSerializer', 'permission_ids', 'permission', True),
    ('apps.core.organization_serializers.DepartmentSerializer', 'parent', 'department', False),
    ('apps.core.organization_serializers.MembershipSerializer', 'department', 'department', False),
    ('apps.core.organization_serializers.ScopeGrantSerializer', 'role', 'role', False),
])
def test_related_ids_are_scoped_when_fields_are_bound_after_module_import(settings, admin_user,
                                                                         serializer_path, field, kind, many):
    from django.utils.module_loading import import_string
    from rest_framework.exceptions import ValidationError

    # 先导入类再激活租户，匹配服务启动后处理请求的真实时序。
    serializer_class = import_string(serializer_path)
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    first = Tenant.objects.create(slug='first', name='本租户')
    second = Tenant.objects.create(slug='second', name='其它租户')

    def related(label):
        if kind == 'role':
            return Role.objects.create(name=label)
        if kind == 'permission':
            return Permission.objects.create(name=label, code=label, resource=label, action='read')
        row = create_row(kind, admin_user, label)
        if kind == 'flow':
            row.status = 'published'
            row.save(update_fields=['status'])
        return row

    with tenant_context(first.pk):
        own = related('own')
    with tenant_context(second.pk):
        foreign = related('foreign')
    with tenant_context(first.pk):
        bound = serializer_class().fields[field]
        value = lambda row: [str(row.pk)] if many else str(row.pk)
        assert bound.run_validation(value(own)) == ([own] if many else own)
        with pytest.raises(ValidationError):
            bound.run_validation(value(foreign))


def test_foreign_flow_submission_is_rejected_before_creating_approval(settings, admin_user):
    from tests.test_advanced_approvals import definition

    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    settings.ROOT_URLCONF = 'tests.tenant_object_urls'
    settings.ADMINCORE_MODULES = ('approvals',)
    first = Tenant.objects.create(slug='first', name='本租户')
    second = Tenant.objects.create(slug='second', name='其它租户')
    with tenant_context(second.pk):
        foreign = ApprovalFlow.objects.create(name='其它流程', code='foreign', created_by=admin_user,
                                             status='published', definition=definition(admin_user))
    client = APIClient()
    client.force_authenticate(admin_user)
    response = client.post('/api/v1/approvals/', {'title': '越界关联', 'content': '内容', 'flow_id': str(foreign.pk)},
                           format='json', HTTP_X_ADMINCORE_TENANT=str(first.pk))
    assert response.status_code == 400, response.data
    assert not ApprovalRequest.all_objects.exists()
