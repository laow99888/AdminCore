from django.db import IntegrityError, transaction
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework import serializers
from drf_spectacular.utils import extend_schema
from apps.auth_app.write_authorization import authorize_write
from apps.permissions.permissions import IsAdmin
from apps.core.mixins import EnvelopeResponseMixin
from apps.core.query_budget import QueryBudgetListMixin, query_budget
from apps.core.list_queries import validate_list_query
from .models import Tenant, TenantMembership
from .tenant_serializers import TenantSerializer, TenantMembershipSerializer


class MyTenantSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    role = serializers.CharField()


class MyTenantView(QueryBudgetListMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MyTenantSerializer
    ordering_fields = ['tenant__name', 'tenant_id']
    ordering = ['tenant__name', 'tenant_id']

    @extend_schema(responses=MyTenantSerializer(many=True))
    def list(self, request):
        validate_list_query(request, self)
        with query_budget():
            memberships = TenantMembership.objects.filter(
                user=request.user, is_active=True, tenant__status=Tenant.STATUS_ACTIVE,
            ).select_related('tenant').order_by(*self.ordering)
            return Response({'code': 200, 'message': 'success', 'data': [
                {'id': str(item.tenant_id), 'slug': item.tenant.slug, 'name': item.tenant.name, 'role': item.role}
                for item in memberships
            ]})

class TenantViewSet(QueryBudgetListMixin, viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [IsAdmin]
    ordering_fields = ['created_at', 'updated_at', 'slug', 'name', 'status']
    ordering = ['name', 'id']
    http_method_names = ['get', 'post', 'patch', 'put', 'head', 'options']

    @transaction.atomic
    def perform_create(self, serializer):
        authorize_write(self.request, admin=True)
        try:
            serializer.save()
        except IntegrityError as exc:
            raise ValidationError({'slug': '租户标识已存在'}) from exc

    @transaction.atomic
    def perform_update(self, serializer):
        authorize_write(self.request, admin=True)
        if serializer.validated_data.get('status') == Tenant.STATUS_CLOSED:
            # 关闭是可逆的状态标记，不删除业务数据；关闭租户不能再建立新成员。
            TenantMembership.objects.filter(tenant=serializer.instance, is_active=True).update(is_active=False)
        serializer.save()

class TenantMembershipViewSet(EnvelopeResponseMixin, viewsets.ModelViewSet):
    queryset = TenantMembership.objects.select_related('tenant', 'user').exclude(user__is_service_account=True)
    serializer_class = TenantMembershipSerializer
    permission_classes = [IsAdmin]
    ordering_fields = ['created_at', 'updated_at', 'role', 'is_active', 'tenant__name', 'user__username']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'patch', 'put', 'delete', 'head', 'options']

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_id = self.request.query_params.get('tenant')
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        authorize_write(self.request, admin=True, related_users=(serializer.validated_data['user'].pk,))
        tenant = Tenant.objects.select_for_update().filter(pk=serializer.validated_data['tenant'].pk).first()
        if tenant is None or tenant.status != Tenant.STATUS_ACTIVE:
            raise ValidationError({'tenant': '租户不存在或已关闭'})
        try:
            serializer.save()
        except IntegrityError as exc:
            raise ValidationError({'user': '用户已经是该租户成员'}) from exc

    @transaction.atomic
    def perform_update(self, serializer):
        authorize_write(self.request, admin=True, related_users=(serializer.instance.user_id,))
        if serializer.validated_data.get('tenant', serializer.instance.tenant).pk != serializer.instance.tenant_id:
            raise ValidationError({'tenant': '成员归属租户不可修改'})
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        authorize_write(self.request, admin=True, related_users=(instance.user_id,))
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
