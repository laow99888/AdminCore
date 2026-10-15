from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view
from apps.core.mixins import EnvelopeResponseMixin
from apps.core.schema import envelope
from apps.core.idempotency import with_idempotency
from .models import Announcement
from .announcement_serializers import AnnouncementSerializer, AnnouncementWriteSerializer, AnnouncementTransitionSerializer
from .announcement_services import authorize, create_announcement, mutate_announcement
from .announcement_content import prepare_content


@extend_schema_view(retrieve=extend_schema(responses=envelope('AnnouncementDetailResponse', AnnouncementSerializer())))
class AnnouncementPublicViewSet(EnvelopeResponseMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    http_method_names = ['get', 'head', 'options']
    permission_classes = [IsAuthenticated]
    serializer_class = AnnouncementSerializer
    search_fields = ['title', 'content']
    ordering_fields = ['published_at']
    ordering = ['-published_at', '-id']
    read_permission = None

    def check_permissions(self, request):
        super().check_permissions(request)
        if self.action in ('list', 'retrieve'):
            # 鉴权先于列表输入校验，保留未授权请求的401/403结果。
            authorize(request, self.read_permission)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Announcement.objects.none()
        return Announcement.objects.filter(status='published')


@extend_schema_view(
    create=extend_schema(request=AnnouncementWriteSerializer, responses={201: envelope('AnnouncementCreatedResponse', AnnouncementSerializer())}),
    partial_update=extend_schema(request=AnnouncementWriteSerializer, responses=envelope('AnnouncementUpdatedResponse', AnnouncementSerializer())),
    publish=extend_schema(request=AnnouncementTransitionSerializer, responses=envelope('AnnouncementPublishedResponse', AnnouncementSerializer())),
    withdraw=extend_schema(request=AnnouncementTransitionSerializer, responses=envelope('AnnouncementWithdrawnResponse', AnnouncementSerializer())),
)
class AnnouncementManageViewSet(AnnouncementPublicViewSet):
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['status']
    ordering_fields = ['created_at', 'updated_at', 'published_at']
    ordering = ['-created_at', '-id']
    read_permission = 'announcement:read'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Announcement.objects.none()
        return Announcement.objects.all()

    def _write(self, request, operation, pk=None):
        code = 'announcement:update' if operation in ('create', 'edit') else 'announcement:publish'
        # Recheck before even replaying an idempotent result; lock actor until mutation commits.
        with transaction.atomic():
            actor = authorize(request, code, lock=True)
            serializer = AnnouncementWriteSerializer(data=request.data) if operation in ('create', 'edit') else AnnouncementTransitionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            def callback():
                row = create_announcement(request, actor, serializer.validated_data) if operation == 'create' else mutate_announcement(request, actor, pk, serializer.validated_data, operation)
                return Response({'code': 200, 'message': 'success', 'data': AnnouncementSerializer(row).data}, status=201 if operation == 'create' else 200)
            response = with_idempotency(request, f'announcements:{pk or "new"}:{operation}', callback)
            # 旧幂等缓存可能早于本次消毒策略；鉴权后同样防御处理返回正文。
            data = dict(response.data['data'])
            data.setdefault('content_format', 'plain')
            data['content'] = prepare_content(data['content'], data['content_format'], validate=False)
            response.data = {**response.data, 'data': data}
            return response

    def create(self, request):
        return self._write(request, 'create')

    def partial_update(self, request, pk=None):
        return self._write(request, 'edit', pk)

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        return self._write(request, 'publish', pk)

    @action(detail=True, methods=['post'])
    def withdraw(self, request, pk=None):
        return self._write(request, 'withdraw', pk)
