from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from django_filters import rest_framework as filters
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.auth_app.write_authorization import authorize_write
from apps.permissions.permissions import IsAdmin
from .appointments import active_on, check_overlap, check_person
from .mixins import EnvelopeResponseMixin
from .models import Department, OrganizationAppointment
from .schema import envelope
from .system_views import VersionConflict, audit


class AppointmentSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    status = serializers.SerializerMethodField()
    version = serializers.IntegerField(min_value=0)

    class Meta:
        model = OrganizationAppointment
        fields = ['id', 'user', 'username', 'department', 'department_name', 'kind', 'starts_on', 'ends_on', 'cancelled', 'reason', 'version', 'status']
        read_only_fields = ['cancelled']

    def get_status(self, row) -> str:
        day = timezone.localdate()
        return 'cancelled' if row.cancelled else 'planned' if row.starts_on > day else 'ended' if row.ends_on and row.ends_on <= day else 'active'

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - {key for key, field in self.fields.items() if not field.read_only}:
            raise ValidationError({'non_field_errors': '任职请求包含未知或只读字段'})
        return super().to_internal_value(data)

    def validate(self, attrs):
        if attrs['version'] != 0:
            raise ValidationError({'version': '新建任职版本必须为 0'})
        if attrs.get('ends_on') is not None and attrs['ends_on'] <= attrs['starts_on']:
            raise ValidationError({'ends_on': '结束日期必须晚于生效日期，结束当天已不任职'})
        return attrs


class AppointmentEndSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    ends_on = serializers.DateField(required=False)
    reason = serializers.CharField(max_length=500)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise ValidationError({'non_field_errors': '任期操作包含未知字段'})
        return super().to_internal_value(data)


class AppointmentFilter(filters.FilterSet):
    as_of = filters.DateFilter(method='at_date')

    class Meta:
        model = OrganizationAppointment
        fields = ['user', 'department', 'kind', 'cancelled']

    def at_date(self, rows, name, day):
        return active_on(rows, day)


@extend_schema_view(retrieve=extend_schema(responses=envelope('AppointmentDetailResponse', AppointmentSerializer())),
                    create=extend_schema(responses={201: envelope('AppointmentCreatedResponse', AppointmentSerializer())}))
class AppointmentViewSet(EnvelopeResponseMixin, mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdmin]
    queryset = OrganizationAppointment.objects.select_related('user', 'department').all()
    serializer_class = AppointmentSerializer
    search_fields = ['user__username', 'department__name']
    filterset_class = AppointmentFilter
    ordering_fields = ['starts_on', 'ends_on', 'created_at']
    http_method_names = ['get', 'post', 'head', 'options']

    @transaction.atomic
    def perform_create(self, serializer):
        values = serializer.validated_data
        authorize_write(self.request, admin=True, related_users=(values['user'].pk,))
        department = get_object_or_404(Department.objects.select_for_update(), pk=values['department'].pk)
        if not department.is_active:
            raise ValidationError('不能任职于停用部门')
        from .tenancy import current_tenant_id, enabled
        tenant_id = current_tenant_id() if enabled() else None
        if str(department.tenant_id or '') != str(tenant_id or ''):
            raise ValidationError('任职部门必须属于当前租户')
        values['user'].refresh_from_db()
        check_person(values['user'], tenant_id)
        check_overlap(values, tenant_id)
        row = serializer.save(version=1)
        audit(self.request, 'appointment', row.pk, None, AppointmentSerializer(row).data)

    def locked(self):
        # 先定位权限范围，随后按公共约定锁用户，再锁任职行。
        original = self.get_object()
        authorize_write(self.request, admin=True, related_users=(original.user_id,))
        return get_object_or_404(OrganizationAppointment.objects.select_for_update(), pk=original.pk)

    @extend_schema(request=AppointmentEndSerializer, responses=envelope('AppointmentEndResponse', AppointmentSerializer()))
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def end(self, request, *args, **kwargs):
        return self.finish(request, cancel=False)

    @extend_schema(request=AppointmentEndSerializer, responses=envelope('AppointmentCancelResponse', AppointmentSerializer()))
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def cancel(self, request, *args, **kwargs):
        return self.finish(request, cancel=True)

    def finish(self, request, *, cancel):
        payload = AppointmentEndSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        values = payload.validated_data
        row = self.locked()
        if row.version != values['version']:
            raise VersionConflict()
        if row.cancelled:
            raise ValidationError('任职已取消')
        before = AppointmentSerializer(row).data
        if cancel:
            if 'ends_on' in values or row.starts_on <= timezone.localdate():
                raise ValidationError('只能取消尚未生效的任职，且不能同时设置结束日期')
            row.cancelled = True
        else:
            day = values.get('ends_on')
            if day is None or day <= row.starts_on or row.ends_on is not None and day >= row.ends_on:
                raise ValidationError('只能将任期缩短，结束日期必须晚于生效日期')
            row.ends_on = day
        row.reason = values['reason']
        row.version += 1
        row.save(update_fields=['ends_on', 'cancelled', 'reason', 'version', 'updated_at'])
        data = AppointmentSerializer(row).data
        audit(request, 'appointment', row.pk, before, data)
        return Response({'code': 200, 'message': 'success', 'data': data})
