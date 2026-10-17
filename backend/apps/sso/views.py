from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiTypes
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth_app.authentication import SessionJWTAuthentication
from apps.auth_app.browser_session import BrowserSessionMixin
from apps.auth_app.models import AuthSession
from apps.auth_app.reauthentication import require_recent_password
from apps.core.modules import module_enabled
from apps.core.query_budget import QueryBudgetListMixin, query_budget
from apps.core.schema import envelope, MessageResponse, BROWSER_SESSION_PARAMETERS
from apps.logs.audit import snapshot, write_audit
from apps.permissions.permissions import HasPermission, IsAdmin, has_permission_code
from . import service
from .configuration import SSOUnavailable, provider
from .models import ExternalIdentity, SSOSession
from .serializers import (AuthorizationSerializer, BindSerializer, CompleteSerializer, CompletedSerializer, ConfigSerializer,
                          IdentitySerializer, StartSerializer, StatusSerializer, UnbindSerializer)


class EnabledMixin:
    def initial(self, request, *args, **kwargs):
        if not module_enabled('sso'):
            raise NotFound()
        if len(request.body) > 8192:
            raise ValidationError('请求大小超过限制')
        super().initial(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        response['Pragma'] = 'no-cache'
        response['Referrer-Policy'] = 'no-referrer'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class PublicView(EnabledMixin, APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get_authenticate_header(self, request):
        # DRF otherwise rewrites anonymous AuthenticationFailed to 403 and loses login feedback semantics.
        return 'SSO'


class ConfigView(PublicView):
    @extend_schema(responses=envelope('SSOConfigResponse', ConfigSerializer()))
    def get(self, request):
        try:
            config = provider()
            data = {'enabled': True, 'label': config.label}
        except SSOUnavailable:
            data = {'enabled': False}
        return Response({'code': 200, 'message': 'success', 'data': data})


def set_cookie(response, name, value, config, maximum):
    response.set_cookie(name, value, max_age=maximum, secure=config.redirect_uri.startswith('https:'),
                        httponly=True, samesite='Lax', path=service.COOKIE_PATH)


class StartView(PublicView):
    @extend_schema(request=StartSerializer, responses=envelope('SSOAuthorizationResponse', AuthorizationSerializer()))
    def post(self, request):
        serializer = StartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config = provider()
        url, cookie = service.start(request, config, serializer.validated_data)
        response = Response({'code': 200, 'message': 'success', 'data': {'authorization_url': url}})
        set_cookie(response, service.BROWSER_COOKIE, cookie, config, 300)
        response.delete_cookie(service.COMPLETION_COOKIE, path=service.COOKIE_PATH, samesite='Lax')
        return response


class CallbackView(PublicView):
    @extend_schema(responses={302: OpenApiTypes.STR})
    def get(self, request):
        config = provider()
        try:
            cookie = service.callback(request, config)
            response = HttpResponseRedirect(config.frontend_origin + '/enterprise-login?result=ready')
            set_cookie(response, service.COMPLETION_COOKIE, cookie, config, 120)
        except (AuthenticationFailed, SSOUnavailable, PermissionDenied):
            service.audit_failure(request, 'callback_rejected')
            response = HttpResponseRedirect(config.frontend_origin + '/enterprise-login?result=failed')
            response.delete_cookie(service.COMPLETION_COOKIE, path=service.COOKIE_PATH, samesite='Lax')
        response.delete_cookie(service.BROWSER_COOKIE, path=service.COOKIE_PATH, samesite='Lax')
        return response


class StatusView(PublicView):
    @extend_schema(responses=envelope('SSOStatusResponse', StatusSerializer()))
    def get(self, request):
        config = provider()
        return Response({'code': 200, 'message': 'success', 'data': service.login_status(request, config)})


class CompleteView(BrowserSessionMixin, PublicView):
    @extend_schema(request=CompleteSerializer, responses=envelope('SSOCompletedResponse', CompletedSerializer()),
                   parameters=BROWSER_SESSION_PARAMETERS)
    def post(self, request):
        serializer = CompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = service.complete(request, provider(), serializer.validated_data)
        response = Response({'code': 200, 'message': 'success', 'data': result})
        response.delete_cookie(service.COMPLETION_COOKIE, path=service.COOKIE_PATH, samesite='Lax')
        return response


class CancelView(PublicView):
    @extend_schema(request=StartSerializer, responses=MessageResponse)
    def post(self, request):
        config = provider()
        service.require_origin(request, config)
        service.limited(request, 'cancel')
        try:
            flow = service.pending(request, config)
            from .models import LoginFlow
            with query_budget():
                LoginFlow.objects.filter(pk=flow.pk, completed_at__isnull=True).update(completed_at=timezone.now(), completion_digest='')
        except AuthenticationFailed:
            pass
        response = Response({'code': 200, 'message': '企业登录已取消', 'data': None})
        for name in (service.BROWSER_COOKIE, service.COMPLETION_COOKIE):
            response.delete_cookie(name, path=service.COOKIE_PATH, samesite='Lax')
        return response


@extend_schema_view(create=extend_schema(request=BindSerializer, responses={201: envelope('SSOBoundResponse', IdentitySerializer())}))
class IdentityViewSet(EnabledMixin, QueryBudgetListMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    authentication_classes = [SessionJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdmin, HasPermission]
    permission_map = {'list': 'sso:read', 'create': 'sso:bind', 'unbind': 'sso:unbind'}
    serializer_class = IdentitySerializer
    filter_backends = []
    lookup_value_regex = '[0-9a-fA-F-]{36}'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ExternalIdentity.objects.none()
        return ExternalIdentity.objects.select_related('user').filter(issuer=provider().issuer)

    def locked_actor(self, request, operation):
        user = get_user_model().objects.select_for_update().filter(pk=request.user.pk).first()
        if user is None or not user.is_active:
            raise AuthenticationFailed('登录凭据已撤销，请重新登录')
        require_recent_password(request, user, 'sso:' + operation)
        if user.must_change_password or not (user.is_staff or user.is_superuser) or not has_permission_code(user, 'sso:' + operation):
            raise PermissionDenied('仅管理员可以管理企业身份绑定')
        return user

    def create(self, request):
        serializer = BindSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values, config = serializer.validated_data, provider()
        try:
            with query_budget(), transaction.atomic():
                # Lock both local accounts by PK so simultaneous cross-admin actions cannot invert locks.
                actors = {user.pk: user for user in get_user_model().objects.select_for_update().filter(
                    pk__in=[request.user.pk, values['user_id']]).order_by('pk')}
                actor = self.locked_actor(request, 'bind')
                target = actors.get(values['user_id'])
                if target is None or not target.is_active or target.must_change_password or not target.has_usable_password():
                    raise ValidationError('只能绑定已启用且已完成初始改密的本地账号')
                if not module_enabled('sso') or provider().fingerprint != config.fingerprint:
                    raise SSOUnavailable()
                # Revoked identities are not silently reassigned to another account or resurrected.
                row = ExternalIdentity.objects.create(user=target, issuer=config.issuer, subject=values['subject'])
                write_audit(resource='sso_identity', identifier=row.pk, action='create', request=request, actor=actor,
                            after=snapshot('sso_identity', row), description='管理员显式绑定已有本地账号与企业 subject')
        except IntegrityError:
            raise ValidationError('该企业身份或本地账号已有绑定记录，请核对 issuer 和 subject') from None
        return Response({'code': 201, 'message': '企业身份已绑定', 'data': IdentitySerializer(row).data}, status=201)

    @extend_schema(request=UnbindSerializer, responses=MessageResponse)
    @action(detail=True, methods=['post'])
    def unbind(self, request, pk=None):
        serializer = UnbindSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = get_object_or_404(self.get_queryset(), pk=pk)
        with query_budget(), transaction.atomic():
            list(get_user_model().objects.select_for_update().filter(pk__in=[request.user.pk, row.user_id]).order_by('pk'))
            actor = self.locked_actor(request, 'unbind')
            row = ExternalIdentity.objects.select_for_update().get(pk=row.pk)
            if row.revoked_at is None:
                before = snapshot('sso_identity', row)
                row.revoked_at = timezone.now()
                row.binding_version += 1
                row.save(update_fields=['revoked_at', 'binding_version'])
                AuthSession.objects.filter(pk__in=SSOSession.objects.filter(identity=row).values('session_id'), revoked_at__isnull=True).update(revoked_at=timezone.now())
                write_audit(resource='sso_identity', identifier=row.pk, request=request, actor=actor,
                            before=before, after=snapshot('sso_identity', row), description='管理员撤销企业身份与企业登录会话')
        return Response({'code': 200, 'message': '企业身份绑定已撤销', 'data': None})
