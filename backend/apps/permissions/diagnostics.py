"""权限策略说明：只解释登记的元数据，不读取或授权任何业务记录。"""
from collections.abc import Mapping

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from apps.auth_app.write_authorization import authorize_write
from apps.core.data_scope import grants_for, scope_queryset
from apps.core.schema import envelope
from apps.core.tenancy import current_tenant_id, enabled
from .field_permissions import canonical_resource, field_policy_registry, resolve_field_policy
from .models import Role
from .permissions import HasPermission, IsAdmin, has_permission_code


class FieldDiagnosticRequest(serializers.Serializer):
    user_id = serializers.UUIDField()
    resource = serializers.CharField(max_length=50)
    field = serializers.CharField(max_length=101)
    operation = serializers.ChoiceField(choices=['read', 'create', 'update'])

    def validate(self, attrs):
        resource = canonical_resource(attrs['resource'])
        registry = field_policy_registry()
        if resource not in registry or attrs['field'] not in registry[resource]:
            raise ValidationError('字段未在资源契约中登记')
        attrs['resource'] = resource
        return attrs


class RoleFieldSource(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    version = serializers.IntegerField()
    active = serializers.BooleanField()
    declared = serializers.BooleanField()
    field_granted = serializers.BooleanField()
    operation_granted = serializers.BooleanField()


class DataScopeSource(serializers.Serializer):
    role_id = serializers.UUIDField()
    active = serializers.BooleanField()
    scope = serializers.CharField()


class FieldDiagnosticResult(serializers.Serializer):
    user_id = serializers.UUIDField()
    resource = serializers.CharField()
    field = serializers.CharField()
    operation = serializers.CharField()
    field_action = serializers.CharField()
    field_allowed = serializers.BooleanField()
    field_reason = serializers.ChoiceField(choices=['administrator', 'legacy_unrestricted', 'explicit_union'])
    permission_code = serializers.CharField(allow_null=True)
    operation_allowed = serializers.BooleanField()
    user_active = serializers.BooleanField()
    must_change_password = serializers.BooleanField()
    module_enabled = serializers.BooleanField()
    requires_admin = serializers.BooleanField()
    roles = RoleFieldSource(many=True)
    data_scope = DataScopeSource(many=True)
    row_access = serializers.ChoiceField(choices=['not_evaluated'])
    tenant_id = serializers.UUIDField(allow_null=True)


def _resource_contract(resource, operation):
    """内置入口的真实动作；业务模块只使用显式登记的同资源权限码。"""
    from apps.core.modules import MODULES, module_enabled
    builtin = {
        'user': ('user', None, {'read': 'read', 'create': 'create', 'update': 'update'}),
        'role': ('role', None, {'read': 'read', 'create': 'update', 'update': 'update'}),
        'post': ('post', 'organization', {'read': 'read', 'create': 'update', 'update': 'update'}),
        'files': ('file', 'files', {'read': 'read'}),
        'logs': ('log', None, {'read': 'read'}),
        'tasks': ('task', 'tasks', {'read': 'read'}),
    }
    if resource in builtin:
        permission_resource, module, actions = builtin[resource]
        action = actions.get(operation)
        return (f'{permission_resource}:{action}' if action else None,
                module is None or module_enabled(module),
                resource == 'post' or (resource == 'role' and operation != 'read'), permission_resource)
    module = next(item for item in MODULES if resource in dict(item.field_policies))
    code = f'{resource}:{operation}'
    return (code if code in {row[3] for row in module.permissions} else None,
            module_enabled(module.key), False, resource)


@transaction.atomic
def explain_field_policy(user, resource, field, operation):
    code, available, requires_admin, scope_resource = _resource_contract(resource, operation)
    action = 'read' if operation == 'read' else 'write'
    administrator = user.is_staff or user.is_superuser
    # 与角色编辑共用角色行锁，避免同次说明混用旧字段策略和新功能权限。
    # 用户锁已由入口按主键排序取得；此处只锁角色本体，保持用户→角色顺序。
    roles = list(Role.objects.select_for_update(of=('self',)).filter(
        userrole__user=user).order_by('pk').prefetch_related('permissions__permission'))
    sources = []
    for role in roles:
        policies = role.field_permissions
        declared = isinstance(policies, Mapping) and resource in policies
        policy = policies.get(resource) if declared else None
        fields = policy.get(action, []) if isinstance(policy, Mapping) else []
        sources.append({'id': role.pk, 'name': role.name, 'version': role.version,
                        'active': role.is_active, 'declared': declared,
                        'field_granted': role.is_active and declared and field in fields,
                        'operation_granted': role.is_active and code is not None and any(
                            item.permission.code == code for item in role.permissions.all())})
    fields, reason = resolve_field_policy(user, resource, action, [role.field_permissions for role in roles if role.is_active])
    field_allowed = field in fields
    operation_allowed = bool(code and available and user.is_active and not user.must_change_password
                             and (administrator or any(source['operation_granted'] for source in sources))
                             and (not requires_admin or administrator))
    return {'user_id': user.pk, 'resource': resource, 'field': field, 'operation': operation,
            'field_action': action, 'field_allowed': field_allowed, 'field_reason': reason,
            'permission_code': code, 'operation_allowed': operation_allowed,
            'user_active': user.is_active, 'must_change_password': user.must_change_password,
            'module_enabled': available, 'requires_admin': requires_admin, 'roles': sources,
            'data_scope': [{'role_id': grant.role_id, 'active': grant.role.is_active, 'scope': grant.scope}
                           for grant in grants_for(user, scope_resource)],
            'row_access': 'not_evaluated', 'tenant_id': current_tenant_id() if enabled() else None}


class FieldDiagnosticView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin, HasPermission]
    required_permission = 'role:read'

    @extend_schema(request=FieldDiagnosticRequest,
                   responses=envelope('FieldDiagnosticResponse', FieldDiagnosticResult()))
    @transaction.atomic
    def post(self, request):
        payload = FieldDiagnosticRequest(data=request.data)
        payload.is_valid(raise_exception=True)
        values = payload.validated_data
        actor = authorize_write(request, 'role:read', admin=True, related_users=(values['user_id'],))
        if not has_permission_code(actor, 'user:read'):
            raise PermissionDenied()
        users = scope_queryset(get_user_model().objects.all(), actor, 'user', 'pk')
        if enabled():
            from apps.core.models import TenantMembership, Tenant
            tenant_id = current_tenant_id()
            if not tenant_id or not Tenant.objects.filter(pk=tenant_id, status=Tenant.STATUS_ACTIVE).exists():
                raise PermissionDenied('请先选择有效租户')
            users = users.filter(pk__in=TenantMembership.objects.filter(
                tenant_id=tenant_id, is_active=True).values('user_id'))
        target = get_object_or_404(users, pk=values['user_id'])
        result = explain_field_policy(target, values['resource'], values['field'], values['operation'])
        return Response({'code': 200, 'message': 'success', 'data': result},
                        headers={'Cache-Control': 'private, no-store'})
