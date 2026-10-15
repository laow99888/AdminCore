from django.db import transaction, IntegrityError
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from apps.permissions.permissions import IsAdmin
from .mixins import EnvelopeResponseMixin
from .models import Department, OrganizationMembership, DataScopeGrant
from .organization_serializers import DepartmentSerializer, MembershipSerializer, ScopeGrantSerializer
from .system_views import VersionConflict, audit
from .schema import envelope, MessageResponse
from drf_spectacular.utils import extend_schema, extend_schema_view


class OrganizationViewSet(EnvelopeResponseMixin, viewsets.ModelViewSet):
    # 组织归属、数据授权都属于权限边界，只允许管理员维护。
    permission_classes = [IsAdmin]


@extend_schema_view(retrieve=extend_schema(responses=envelope('DepartmentDetailResponse', DepartmentSerializer())),
                    create=extend_schema(responses={201: envelope('DepartmentCreatedResponse', DepartmentSerializer())}),
                    update=extend_schema(responses=envelope('DepartmentUpdatedResponse', DepartmentSerializer())),
                    partial_update=extend_schema(responses=envelope('DepartmentPatchedResponse', DepartmentSerializer())),
                    destroy=extend_schema(responses=MessageResponse))
class DepartmentViewSet(OrganizationViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    search_fields = ['name']
    ordering_fields = ['order', 'name', 'created_at']

    def lock_tree(self):
        return {row.pk: row for row in Department.objects.select_for_update().order_by('pk')}

    def validate_tree(self, serializer, rows):
        parent = serializer.validated_data.get('parent', serializer.instance.parent if serializer.instance else None)
        visited = set()
        while parent:
            if parent.pk in visited or (serializer.instance and parent.pk == serializer.instance.pk):
                raise ValidationError({'parent': '部门不能形成循环'})
            visited.add(parent.pk)
            current = rows.get(parent.pk)
            if current is None or not current.is_active:
                raise ValidationError({'parent': '上级部门不存在或已停用'})
            parent = rows.get(current.parent_id)

    @transaction.atomic
    def perform_create(self, serializer):
        rows = self.lock_tree()
        self.validate_tree(serializer, rows)
        if serializer.validated_data['version'] != 0:
            raise ValidationError({'version': '新建部门版本必须为 0'})
        row = serializer.save(version=1)
        audit(self.request, 'department', row.pk, None, DepartmentSerializer(row).data)

    @transaction.atomic
    def perform_update(self, serializer):
        rows = self.lock_tree()
        row = rows.get(serializer.instance.pk)
        if row is None or serializer.validated_data.get('version') != row.version:
            raise VersionConflict()
        serializer.instance = row
        self.validate_tree(serializer, rows)
        if serializer.validated_data.get('is_active') is False and row.children.filter(is_active=True).exists():
            raise ValidationError({'is_active': '请先停用或调整下级部门'})
        before = DepartmentSerializer(row).data
        row = serializer.save(version=row.version + 1)
        audit(self.request, 'department', row.pk, before, DepartmentSerializer(row).data)

    @transaction.atomic
    def perform_destroy(self, instance):
        rows = self.lock_tree()
        row = rows.get(instance.pk)
        if row is None:
            raise VersionConflict()
        if row.children.exists() or row.members.exists() or row.datascopegrant_set.exists():
            raise ValidationError('部门仍有关联数据，请调整关联或停用部门')
        before = DepartmentSerializer(row).data
        row.delete()
        audit(self.request, 'department', instance.pk, before, None)


@extend_schema_view(retrieve=extend_schema(responses=envelope('MembershipDetailResponse', MembershipSerializer())),
                    create=extend_schema(responses={201: envelope('MembershipCreatedResponse', MembershipSerializer())}),
                    update=extend_schema(responses=envelope('MembershipUpdatedResponse', MembershipSerializer())),
                    partial_update=extend_schema(responses=envelope('MembershipPatchedResponse', MembershipSerializer())),
                    destroy=extend_schema(responses=MessageResponse))
class MembershipViewSet(OrganizationViewSet):
    queryset = OrganizationMembership.objects.select_related('user', 'department').all()
    serializer_class = MembershipSerializer
    search_fields = ['user__username']
    filterset_fields = ['department', 'user']
    ordering_fields = ['created_at', 'user__username', 'department__name']

    @transaction.atomic
    def perform_create(self, serializer):
        if serializer.validated_data['version'] != 0:
            raise ValidationError({'version': '新建归属版本必须为 0'})
        department = Department.objects.select_for_update().get(pk=serializer.validated_data['department'].pk)
        if not department.is_active:
            raise ValidationError({'department': '部门已停用'})
        try:
            with transaction.atomic():
                row = serializer.save(version=1)
        except IntegrityError as exc:
            raise ValidationError({'user': '此用户已有部门归属，请编辑现有记录'}) from exc
        audit(self.request, 'membership', row.pk, None, MembershipSerializer(row).data)

    @transaction.atomic
    def perform_update(self, serializer):
        list(Department.objects.select_for_update().order_by('pk'))
        current = OrganizationMembership.objects.select_for_update().get(pk=serializer.instance.pk)
        if serializer.validated_data.get('version') != current.version:
            raise VersionConflict()
        serializer.instance = current
        if serializer.validated_data.get('user', current.user) != current.user:
            raise ValidationError({'user': '不能变更归属记录的用户'})
        department = serializer.validated_data.get('department', current.department)
        if not Department.objects.filter(pk=department.pk, is_active=True).exists():
            raise ValidationError({'department': '部门已停用'})
        before = MembershipSerializer(current).data
        row = serializer.save(version=current.version + 1)
        audit(self.request, 'membership', row.pk, before, MembershipSerializer(row).data)

    @transaction.atomic
    def perform_destroy(self, instance):
        before = MembershipSerializer(instance).data
        identifier = instance.pk
        instance.delete()
        audit(self.request, 'membership', identifier, before, None)


@extend_schema_view(retrieve=extend_schema(responses=envelope('ScopeDetailResponse', ScopeGrantSerializer())),
                    create=extend_schema(responses={201: envelope('ScopeCreatedResponse', ScopeGrantSerializer())}),
                    update=extend_schema(responses=envelope('ScopeUpdatedResponse', ScopeGrantSerializer())),
                    partial_update=extend_schema(responses=envelope('ScopePatchedResponse', ScopeGrantSerializer())))
class ScopeGrantViewSet(OrganizationViewSet):
    queryset = DataScopeGrant.objects.select_related('role').prefetch_related('departments').all()
    serializer_class = ScopeGrantSerializer
    filterset_fields = ['role', 'resource']
    ordering_fields = ['created_at', 'resource', 'role__name']
    http_method_names = ['get', 'post', 'patch', 'put', 'head', 'options']

    def lock_departments(self, serializer):
        # 与部门停用/删除采用相同顺序加锁，防止校验后部门状态改变。
        rows = {row.pk: row for row in Department.objects.select_for_update().order_by('pk')}
        selected = serializer.validated_data.get('departments')
        if selected is None and serializer.instance:
            selected = serializer.instance.departments.all()
        for department in selected or []:
            if department.pk not in rows or not rows[department.pk].is_active:
                raise ValidationError({'departments': '授权部门不存在或已停用'})

    @transaction.atomic
    def perform_create(self, serializer):
        self.lock_departments(serializer)
        if serializer.validated_data['version'] != 0:
            raise ValidationError({'version': '新建规则版本必须为 0'})
        try:
            with transaction.atomic():
                row = serializer.save(version=1)
        except IntegrityError as exc:
            raise ValidationError({'role': '此角色已有该资源的数据范围，请编辑现有规则'}) from exc
        audit(self.request, 'data_scope', row.pk, None, ScopeGrantSerializer(row).data)

    @transaction.atomic
    def perform_update(self, serializer):
        self.lock_departments(serializer)
        current = DataScopeGrant.objects.select_for_update().get(pk=serializer.instance.pk)
        if serializer.validated_data.get('version') != current.version:
            raise VersionConflict()
        before = ScopeGrantSerializer(current).data
        serializer.instance = current
        row = serializer.save(version=current.version + 1)
        audit(self.request, 'data_scope', row.pk, before, ScopeGrantSerializer(row).data)
