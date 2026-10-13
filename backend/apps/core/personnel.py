"""人员选择目录与最终提交共享查询策略；输出仅含选择所需资料。"""
from django.contrib.auth import get_user_model
from django.db.models import Q, Value
from django.db.models.functions import Concat
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .data_scope import scope_queryset
from .models import Department
from .modules import module_enabled
from .pagination import StandardPagination


def candidates(actor):
    return scope_queryset(get_user_model().objects.filter(is_active=True), actor, 'user', 'pk')


class PersonSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ['id', 'username', 'display_name', 'department', 'department_name']

    @extend_schema_field(serializers.CharField())
    def get_display_name(self, row):
        return row.get_full_name() or row.username

    def membership(self, row):
        if not module_enabled('organization'):
            return None
        membership = getattr(row, 'organization_membership', None)
        return membership if membership and membership.department.is_active else None

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_department(self, row):
        membership = self.membership(row)
        return membership.department_id if membership else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_department_name(self, row):
        membership = self.membership(row)
        return membership.department.name if membership else None


class PeopleQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=100, default='')
    department = serializers.UUIDField(required=False)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)


class PeoplePaginationSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_pages = serializers.IntegerField()


class PeoplePageSerializer(serializers.Serializer):
    items = PersonSerializer(many=True)
    pagination = PeoplePaginationSerializer()


class PickerDepartmentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    parent = serializers.UUIDField(allow_null=True)


class PickerDepartmentsSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    truncated = serializers.BooleanField()
    items = PickerDepartmentSerializer(many=True)


def people_response(request, view):
    query = PeopleQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    params = query.validated_data
    rows = candidates(request.user).select_related('organization_membership__department').order_by('username', 'id')
    if params['search']:
        value = params['search']
        rows = rows.annotate(picker_name=Concat('first_name', Value(' '), 'last_name')).filter(
            Q(username__icontains=value) | Q(first_name__icontains=value) | Q(last_name__icontains=value) | Q(picker_name__icontains=value))
    if params.get('department'):
        if not module_enabled('organization'):
            raise ValidationError({'department': '组织模块未启用，请使用姓名或用户名搜索'})
        # 仅按选择部门精确筛选；后代通过树分别选择，不能绕过人员数据范围。
        rows = rows.filter(organization_membership__department_id=params['department'], organization_membership__department__is_active=True)
    paginator = StandardPagination()
    page = paginator.paginate_queryset(rows, request, view=view)
    response = paginator.get_paginated_response(PersonSerializer(page, many=True).data)
    response['Cache-Control'] = 'private, no-store'
    return response


def picker_departments(actor):
    if not module_enabled('organization'):
        return {'enabled': False, 'truncated': False, 'items': []}
    # 只显示可选人员实际所属部门，不把不可见上级的名字带出授权范围。
    visible_users = candidates(actor).values('pk')
    rows = list(Department.objects.filter(is_active=True, members__user_id__in=visible_users)
                .distinct().order_by('order', 'name', 'id').values('id', 'name', 'parent_id')[:1001])
    truncated = len(rows) > 1000
    rows = rows[:1000]
    ids = {row['id'] for row in rows}
    return {'enabled': True, 'truncated': truncated, 'items': [
        {'id': row['id'], 'name': row['name'], 'parent': row['parent_id'] if row['parent_id'] in ids else None} for row in rows
    ]}
