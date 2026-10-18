from rest_framework import serializers
from .models import Department, OrganizationMembership, DataScopeGrant
from .serializer_fields import TenantPrimaryKeyRelatedField


class DepartmentSerializer(serializers.ModelSerializer):
    version = serializers.IntegerField(min_value=0)
    leader_name = serializers.CharField(source='leader.username', read_only=True, default=None)

    class Meta:
        model = Department
        fields = ('id', 'name', 'parent', 'order', 'is_active', 'version', 'leader', 'leader_name')

    def validate_leader(self, value):
        if value:
            from .appointments import check_person
            from .tenancy import current_tenant_id, enabled
            check_person(value, current_tenant_id() if enabled() else None)
        return value


class MembershipSerializer(serializers.ModelSerializer):
    version = serializers.IntegerField(min_value=0)
    username = serializers.CharField(source='user.username', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = ('id', 'user', 'username', 'department', 'department_name', 'version')

    def validate_user(self, value):
        if value.is_service_account:
            raise serializers.ValidationError('机器身份不能作为组织人员')
        return value

    def validate_department(self, value):
        if not value.is_active:
            raise serializers.ValidationError('不能分配到停用部门')
        return value


class ScopeGrantSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.name', read_only=True)
    version = serializers.IntegerField(min_value=0)
    departments = TenantPrimaryKeyRelatedField(queryset=Department.objects.filter(is_active=True), many=True, required=False)

    class Meta:
        model = DataScopeGrant
        fields = ('id', 'role', 'role_name', 'resource', 'scope', 'departments', 'version')

    def validate(self, attrs):
        if self.instance and (attrs.get('role', self.instance.role) != self.instance.role
                              or attrs.get('resource', self.instance.resource) != self.instance.resource):
            raise serializers.ValidationError('已有规则的角色和资源不可修改')
        scope = attrs.get('scope', self.instance.scope if self.instance else 'self')
        departments = attrs.get('departments', list(self.instance.departments.all()) if self.instance else [])
        if len({department.pk for department in departments}) != len(departments):
            raise serializers.ValidationError({'departments': '部门不能重复'})
        if scope == 'custom' and not departments:
            raise serializers.ValidationError({'departments': '自定义范围必须选择部门'})
        if scope != 'custom' and departments:
            raise serializers.ValidationError({'departments': '仅自定义范围允许选择部门'})
        return attrs
