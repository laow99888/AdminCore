"""固定租户机器身份的独立管理员入口，仅发放已有只读能力。"""
import secrets
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.auth_app.authentication import SessionJWTAuthentication
from apps.auth_app.reauthentication import require_recent_password
from apps.core.exceptions import APIError
from apps.core.models import Tenant, TenantMembership
from apps.core.schema import envelope
from apps.core.tenancy import current_tenant_id, enabled
from apps.logs.audit import write_audit
from apps.permissions.models import Role, RolePermission, UserRole
from apps.permissions.permissions import HasPermission, has_permission_code
from .authentication import digest
from .models import APICredential, ServiceIdentity
from .policy import MAX_ACTIVE_CREDENTIALS, available_scopes
from .serializers import CredentialIssuedSerializer, CredentialSerializer
from .service_serializers import (IdentitySerializer, IdentityCreateSerializer, IdentityUpdateSerializer,
    IdentityCredentialCreateSerializer, IdentityCredentialActionSerializer, IdentityRoleSerializer)
from .views import EnabledNoStoreMixin


@extend_schema_view(
    create=extend_schema(request=IdentityCreateSerializer, responses={201: envelope('ServiceIdentityCreated', IdentitySerializer())}),
    partial_update=extend_schema(request=IdentityUpdateSerializer, responses=envelope('ServiceIdentityUpdated', IdentitySerializer())),
)
class ServiceIdentityViewSet(EnabledNoStoreMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                             viewsets.GenericViewSet):
    authentication_classes = [SessionJWTAuthentication]
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'api_credential:manage'
    serializer_class = IdentitySerializer
    filter_backends = []
    lookup_value_regex = '[0-9a-fA-F-]{36}'
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied('只有当前管理员可以管理机器身份')

    def get_queryset(self):
        return ServiceIdentity.objects.filter(tenant_id=current_tenant_id() if enabled() else None).select_related('user')

    def locked_actor(self, request):
        actor = get_user_model().objects.select_for_update().filter(pk=request.user.pk).first()
        if actor is None or not actor.is_active or actor.is_service_account:
            raise AuthenticationFailed('登录凭据已撤销，请重新登录')
        require_recent_password(request, actor, 'api_credential:manage')
        if actor.must_change_password or not (actor.is_staff or actor.is_superuser) or not has_permission_code(actor, self.required_permission):
            raise PermissionDenied('没有机器身份管理权限')
        tenant = current_tenant_id() if enabled() else None
        if enabled() and tenant is None:
            raise ValidationError('请先选择机器身份所属租户')
        if tenant is not None:
            get_object_or_404(Tenant.objects, pk=tenant, status=Tenant.STATUS_ACTIVE)
        return actor

    def authorized_roles(self, identifiers, actor, lock=False):
        if len(set(identifiers)) != len(identifiers):
            raise ValidationError({'role_ids': '角色不能重复'})
        tenant = current_tenant_id() if enabled() else None
        rows = Role.all_objects.filter(pk__in=identifiers, tenant_id=tenant, is_active=True).order_by('pk')
        if lock:
            rows = rows.select_for_update()
        roles = list(rows)
        if len(roles) != len(identifiers):
            raise ValidationError({'role_ids': '角色不存在、未启用或不属于当前租户'})
        codes = set(RolePermission.all_objects.filter(role__in=roles).values_list('permission__code', flat=True))
        if not codes or not codes <= set(available_scopes()) or any(not has_permission_code(actor, code) for code in codes):
            raise PermissionDenied('机器身份只能使用当前管理员可授予的专用只读角色')
        return roles

    def locked_target(self, identifier):
        # 和凭证认证保持目标 User → Identity → Credential 的顺序。
        get_object_or_404(get_user_model().objects.select_for_update(), pk=identifier, is_service_account=True)
        if enabled() and current_tenant_id() is not None:
            get_object_or_404(Tenant.objects.select_for_update(), pk=current_tenant_id(), status=Tenant.STATUS_ACTIVE)
        return get_object_or_404(self.get_queryset().select_for_update(), pk=identifier)

    def audit(self, request, actor, row, operation, **extra):
        write_audit(request=request, actor=actor, resource='service_identity', identifier=row.pk,
                    action=operation, after={'id': str(row.pk), 'tenant_id': str(row.tenant_id) if row.tenant_id else None,
                    'version': row.version, 'is_active': row.user.is_active, **extra}, description='机器身份' + operation)

    @transaction.atomic
    def create(self, request):
        values = IdentityCreateSerializer(data=request.data)
        values.is_valid(raise_exception=True)
        actor = self.locked_actor(request)
        if enabled():
            get_object_or_404(Tenant.objects.select_for_update(), pk=current_tenant_id(), status=Tenant.STATUS_ACTIVE)
        roles = self.authorized_roles(values.validated_data['role_ids'], actor, lock=True)
        if not enabled() and connection.vendor == 'postgresql':
            # 无租户行可锁时，用事务级共享命名空间串行化不同管理员的配额检查。
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [0x41434D414348494E])
        if self.get_queryset().count() >= 100:
            raise ValidationError('当前租户最多100个机器身份，请停用并复用已有身份')
        user = get_user_model()(username='svc_' + uuid4().hex, is_service_account=True)
        user.set_unusable_password()
        user.save()
        tenant = current_tenant_id() if enabled() else None
        row = ServiceIdentity.objects.create(user=user, tenant_id=tenant, created_by=actor,
            name=values.validated_data['name'], description=values.validated_data['description'])
        UserRole.objects.bulk_create([UserRole(user=user, role=role, tenant_id=tenant) for role in roles])
        if tenant is not None:
            TenantMembership.objects.create(tenant_id=tenant, user=user, role='member')
        self.audit(request, actor, row, 'create', role_ids=[str(role.pk) for role in roles])
        return Response({'code': 201, 'message': '机器身份已创建，不能用于交互登录', 'data': IdentitySerializer(row).data}, status=201)

    @transaction.atomic
    def partial_update(self, request, pk=None):
        serializer = IdentityUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self.locked_actor(request)
        row = self.locked_target(pk)
        values = serializer.validated_data
        if row.version != values['version']:
            raise APIError('机器身份已变更，请刷新后再试', status_code=409)
        if 'role_ids' in values:
            roles = self.authorized_roles(values['role_ids'], actor, lock=True)
            UserRole.all_objects.filter(user=row.user).delete()
            UserRole.objects.bulk_create([UserRole(user=row.user, role=role, tenant_id=row.tenant_id) for role in roles])
        if 'is_active' in values:
            row.user.is_active = values['is_active']
            row.user.save(update_fields=['is_active', 'session_version'])
        for key in ('name', 'description'):
            if key in values:
                setattr(row, key, values[key])
        row.version += 1
        row.save(update_fields=['name', 'description', 'version'])
        self.audit(request, actor, row, 'update', role_ids=IdentitySerializer(row).data['role_ids'])
        return Response({'code': 200, 'message': '机器身份已更新', 'data': IdentitySerializer(row).data})

    @extend_schema(responses=envelope('ServiceIdentityRoles', IdentityRoleSerializer(many=True)))
    @action(detail=False, methods=['get'])
    def roles(self, request):
        candidates = Role.all_objects.filter(tenant_id=current_tenant_id() if enabled() else None, is_active=True).order_by('name')[:201]
        result = []
        for row in candidates:
            try:
                self.authorized_roles([row.pk], request.user)
            except PermissionDenied:
                continue
            result.append({'id': str(row.pk), 'name': row.name})
        return Response({'code': 200, 'message': 'success', 'data': result})

    @extend_schema(responses=envelope('ServiceIdentityCredentials', CredentialSerializer(many=True)))
    @action(detail=True, methods=['get'])
    def credentials(self, request, pk=None):
        row = self.get_object()
        rows = APICredential.objects.filter(owner_id=row.pk).order_by('-created_at', '-pk')[:100]
        return Response({'code': 200, 'message': 'success', 'data': CredentialSerializer(rows, many=True).data})

    @extend_schema(request=IdentityCredentialCreateSerializer, responses={201: envelope('ServiceIdentityCredentialIssued', CredentialIssuedSerializer())})
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def issue(self, request, pk=None):
        serializer = IdentityCredentialCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self.locked_actor(request)
        row = self.locked_target(pk)
        user, values = row.user, serializer.validated_data
        self.authorized_roles(list(UserRole.all_objects.filter(user=user).values_list('role_id', flat=True)), actor, lock=True)
        if not user.is_active or any(not has_permission_code(user, scope) or not has_permission_code(actor, scope) for scope in values['scopes']):
            raise PermissionDenied('机器身份或其只读能力已失效')
        if APICredential.objects.filter(owner=user, revoked_at__isnull=True, expires_at__gt=timezone.now()).count() >= MAX_ACTIVE_CREDENTIALS:
            raise ValidationError('有效开放凭证最多20个')
        secret = secrets.token_urlsafe(32)
        credential = APICredential.objects.create(owner=user, name=values['name'], scopes=values['scopes'], expires_at=values['expires_at'],
            secret_digest=digest(secret), password_digest='', session_version=user.session_version)
        self.audit(request, actor, row, 'create', credential_id=str(credential.pk))
        return Response({'code': 201, 'message': '密钥仅展示一次，请妥善保存',
                         'data': {**CredentialSerializer(credential).data, 'token': f'ac_{credential.pk.hex}.{secret}'}}, status=201)

    def credential_action(self, request, pk, rotate):
        serializer = IdentityCredentialActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self.locked_actor(request)
        row = self.locked_target(pk)
        values = serializer.validated_data
        credential = get_object_or_404(APICredential.objects.select_for_update(), pk=values['credential_id'], owner_id=row.pk)
        if credential.version != values['version']:
            raise APIError('凭证已变更，请刷新后再试', status_code=409)
        if rotate:
            if (not row.user.is_active or credential.revoked_at or credential.expires_at <= timezone.now()
                    or credential.session_version != row.user.session_version
                    or any(scope not in available_scopes() or not has_permission_code(row.user, scope)
                           or not has_permission_code(actor, scope) for scope in credential.scopes)):
                raise PermissionDenied('凭证授权已失效，请重新签发')
            secret = secrets.token_urlsafe(32)
            credential.secret_digest, credential.rotated_at = digest(secret), timezone.now()
            credential.version += 1
            credential.save(update_fields=['secret_digest', 'rotated_at', 'version'])
        elif credential.revoked_at is None:
            credential.revoked_at = timezone.now()
            credential.version += 1
            credential.save(update_fields=['revoked_at', 'version'])
        self.audit(request, actor, row, 'update', credential_id=str(credential.pk), credential_action='rotate' if rotate else 'revoke')
        data = CredentialSerializer(credential).data
        if rotate:
            data = {**data, 'token': f'ac_{credential.pk.hex}.{secret}'}
        return Response({'code': 200, 'message': '旧密钥已失效' if rotate else '凭证已撤销', 'data': data})

    @extend_schema(request=IdentityCredentialActionSerializer, responses=envelope('ServiceCredentialRotated', CredentialIssuedSerializer()))
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def rotate(self, request, pk=None):
        return self.credential_action(request, pk, True)

    @extend_schema(request=IdentityCredentialActionSerializer, responses=envelope('ServiceCredentialRevoked', CredentialSerializer()))
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def revoke(self, request, pk=None):
        return self.credential_action(request, pk, False)
