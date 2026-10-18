import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.auth_app.authentication import SessionJWTAuthentication
from apps.auth_app.reauthentication import require_recent_password
from apps.auth_app.session_views import PasswordConfirmationSerializer
from apps.core.data_scope import scope_queryset
from apps.core.exceptions import APIError
from apps.core.modules import module_enabled
from apps.core.query_budget import QueryBudgetListMixin
from apps.core.schema import MessageResponse, envelope
from apps.logs.audit import snapshot, write_audit
from apps.permissions.permissions import HasPermission, has_permission_code
from .authentication import APICredentialAuthentication, digest
from .models import APICredential
from .policy import MAX_ACTIVE_CREDENTIALS, available_scopes
from .serializers import (AvailableScopeSerializer, CredentialCreateSerializer, CredentialIssuedSerializer,
                          CredentialSerializer, CredentialRotateSerializer, CredentialUsageSerializer)


class EnabledNoStoreMixin:
    def initial(self, request, *args, **kwargs):
        if not module_enabled('api_credentials'):
            raise NotFound()
        super().initial(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        response['Pragma'] = 'no-cache'
        return response


@extend_schema_view(
    create=extend_schema(request=CredentialCreateSerializer, responses={201: envelope('CredentialIssuedResponse', CredentialIssuedSerializer())}),
)
class CredentialViewSet(EnabledNoStoreMixin, QueryBudgetListMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    authentication_classes = [SessionJWTAuthentication]
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'list': 'api_credential:read', 'scopes': 'api_credential:create',
                      'create': 'api_credential:create', 'revoke': 'api_credential:revoke',
                      'rotate': 'api_credential:create', 'statistics': 'api_credential:read'}
    serializer_class = CredentialSerializer
    filter_backends = []
    lookup_value_regex = '[0-9a-fA-F-]{36}'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return APICredential.objects.none()
        return APICredential.objects.filter(owner=self.request.user)

    def locked_actor(self, request, operation):
        actor = get_user_model().objects.select_for_update().filter(pk=request.user.pk).first()
        if actor is None or not actor.is_active:
            raise AuthenticationFailed('登录凭据已撤销，请重新登录')
        require_recent_password(request, actor, 'api_credential:' + operation)
        if actor.must_change_password or not has_permission_code(actor, 'api_credential:' + operation):
            raise PermissionDenied('没有开放凭证管理权限')
        return actor

    @transaction.atomic
    def create(self, request):
        serializer = CredentialCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self.locked_actor(request, 'create')
        values = serializer.validated_data
        if any(not has_permission_code(actor, scope) for scope in values['scopes']):
            raise PermissionDenied('不能签发当前账户没有的能力')
        if APICredential.objects.filter(owner=actor, revoked_at__isnull=True, expires_at__gt=timezone.now()).count() >= MAX_ACTIVE_CREDENTIALS:
            raise ValidationError('有效开放凭证最多20个，请先撤销旧凭证')
        secret = secrets.token_urlsafe(32)
        row = APICredential.objects.create(owner=actor, name=values['name'], scopes=values['scopes'],
            expires_at=values['expires_at'], secret_digest=digest(secret), password_digest=digest(actor.password),
            session_version=actor.session_version)
        write_audit(resource='api_credential', identifier=row.pk, action='create', request=request,
                    actor=actor, after=snapshot('api_credential', row), description='创建本人只读开放凭证')
        data = dict(CredentialSerializer(row).data)
        data['token'] = f'ac_{row.pk.hex}.{secret}'
        return Response({'code': 201, 'message': '密钥仅展示一次，请妥善保存', 'data': data}, status=201)

    @extend_schema(responses=envelope('CredentialScopes', AvailableScopeSerializer(many=True)))
    @action(detail=False, methods=['get'])
    def scopes(self, request):
        values = [{'code': code, 'label': label} for code, label in available_scopes().items()
                  if has_permission_code(request.user, code)]
        return Response({'code': 200, 'message': 'success', 'data': values})

    @extend_schema(request=CredentialRotateSerializer,
                   responses=envelope('CredentialRotatedResponse', CredentialIssuedSerializer()))
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def rotate(self, request, pk=None):
        serializer = CredentialRotateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self.locked_actor(request, 'create')
        if not has_permission_code(actor, 'api_credential:revoke'):
            raise PermissionDenied('轮换需要创建和撤销凭证权限')
        row = get_object_or_404(APICredential.objects.select_for_update().filter(owner=actor), pk=pk)
        if row.version != serializer.validated_data['version']:
            raise APIError('凭证已变更，请刷新后再轮换', status_code=409)
        if row.revoked_at is not None or row.expires_at <= timezone.now():
            raise ValidationError('已撤销或已到期的凭证不能轮换')
        if (row.session_version != actor.session_version or row.password_digest != digest(actor.password)
                or any(scope not in available_scopes() or not has_permission_code(actor, scope) for scope in row.scopes)):
            raise PermissionDenied('凭证授权已失效，请重新创建')
        before = snapshot('api_credential', row)
        secret = secrets.token_urlsafe(32)
        row.secret_digest, row.rotated_at = digest(secret), timezone.now()
        row.version += 1
        row.save(update_fields=['secret_digest', 'rotated_at', 'version'])
        write_audit(resource='api_credential', identifier=row.pk, action='update', request=request, actor=actor,
                    before=before, after=snapshot('api_credential', row), description='轮换本人开放凭证，旧密钥立即失效')
        return Response({'code': 200, 'message': '旧密钥已失效，新密钥仅展示一次',
                         'data': {**CredentialSerializer(row).data, 'token': f'ac_{row.pk.hex}.{secret}'}})

    @extend_schema(parameters=[OpenApiParameter('days', int, description='统计最近1至90个UTC自然日，默认7天')],
                   responses=envelope('CredentialUsageResponse', CredentialUsageSerializer()))
    @action(detail=True, methods=['get'])
    @transaction.atomic
    def statistics(self, request, pk=None):
        if set(request.query_params) - {'days'} or any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise ValidationError('调用统计只接受单个days参数')
        raw = request.query_params.get('days', '7')
        if not 1 <= len(raw) <= 2 or not raw.isascii() or not raw.isdecimal() or not 1 <= int(raw) <= 90:
            raise ValidationError('调用统计天数为1至90')
        days = int(raw)
        row = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
        today = timezone.now().date()
        first = today - timedelta(days=days - 1)
        daily = list(row.daily_usage.filter(day__gte=first, day__lte=today).order_by('day').values('day', 'requests'))
        return Response({'code': 200, 'message': 'success', 'data': {'days': days, 'timezone': 'UTC',
            'statistics_started_at': row.statistics_started_at, 'accepted_requests': row.accepted_requests,
            'recent_requests': sum(item['requests'] for item in daily), 'daily': daily}})

    @extend_schema(request=PasswordConfirmationSerializer, responses=MessageResponse)
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def revoke(self, request, pk=None):
        actor = self.locked_actor(request, 'revoke')
        row = get_object_or_404(APICredential.objects.select_for_update().filter(owner=actor), pk=pk)
        if row.revoked_at is None:
            before = snapshot('api_credential', row)
            row.revoked_at = timezone.now()
            row.save(update_fields=['revoked_at'])
            write_audit(resource='api_credential', identifier=row.pk, request=request, actor=actor,
                        before=before, after=snapshot('api_credential', row), description='撤销本人只读开放凭证')
        return Response({'code': 200, 'message': '开放凭证已撤销', 'data': None})


class GatewayBase(EnabledNoStoreMixin, QueryBudgetListMixin, viewsets.ReadOnlyModelViewSet):
    authentication_classes = [APICredentialAuthentication]
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'head', 'options']
    lookup_value_regex = '[0-9a-fA-F-]{36}'

    def retrieve(self, request, *args, **kwargs):
        return Response({'code': 200, 'message': 'success', 'data': self.get_serializer(self.get_object()).data})


class TaskSummarySerializer(serializers.ModelSerializer):
    class Meta:
        from apps.tasks.models import TaskRecord
        model = TaskRecord
        fields = ('id', 'name', 'task_type', 'status', 'progress', 'created_at', 'started_at', 'completed_at')
        read_only_fields = fields


@extend_schema_view(retrieve=extend_schema(responses=envelope('GatewayTaskDetail', TaskSummarySerializer())))
class TaskGatewayViewSet(GatewayBase):
    serializer_class = TaskSummarySerializer
    credential_scope = 'task:read'
    filterset_fields = ['status', 'task_type']
    search_fields = ['name']
    ordering_fields = ['created_at', 'started_at', 'completed_at']
    ordering = ['-created_at']

    def get_queryset(self):
        from apps.tasks.models import TaskRecord
        if getattr(self, 'swagger_fake_view', False):
            return TaskRecord.objects.none()
        return scope_queryset(TaskRecord.objects.only(*TaskSummarySerializer.Meta.fields), self.request.user, 'task', 'creator_id')


class WorkItemSummarySerializer(serializers.ModelSerializer):
    class Meta:
        from apps.example.models import WorkItem
        model = WorkItem
        fields = ('id', 'title', 'status', 'priority', 'version', 'created_at', 'updated_at')
        read_only_fields = fields


@extend_schema_view(retrieve=extend_schema(responses=envelope('GatewayWorkItemDetail', WorkItemSummarySerializer())))
class WorkItemGatewayViewSet(GatewayBase):
    serializer_class = WorkItemSummarySerializer
    credential_scope = 'example:read'
    filterset_fields = ['status', 'priority']
    search_fields = ['title']
    ordering_fields = ['created_at', 'updated_at', 'priority']
    ordering = ['-created_at']

    def get_queryset(self):
        from apps.example.models import WorkItem
        if getattr(self, 'swagger_fake_view', False):
            return WorkItem.objects.none()
        return scope_queryset(WorkItem.objects.only(*WorkItemSummarySerializer.Meta.fields), self.request.user, 'example', 'creator_id', fallback='self')
