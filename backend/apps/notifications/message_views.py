from django.db import IntegrityError, transaction
from django.db.models import F, Prefetch
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from apps.core.idempotency import with_idempotency
from apps.core.mixins import EnvelopeResponseMixin
from apps.core.schema import envelope
from apps.core.personnel import people_response, picker_departments, PeopleQuerySerializer, PeoplePageSerializer, PickerDepartmentsSerializer
from .announcement_services import authorize
from .models import MessageTemplate, MessageTemplateVersion, MessageDelivery
from .message_channels import enabled, CHANNELS
from .message_services import save_template, submit, render, retry_delivery
from .message_serializers import (MessageTemplateSerializer, TemplateVersionSerializer, TemplateWriteSerializer,
    TemplatePreviewSerializer, TemplateSendSerializer, MessageDeliverySerializer, MessagePreviewResultSerializer,
    ChannelsResultSerializer, SentDeliveriesSerializer, MessageVersionPageSerializer)


class PrivateMessagesMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('MessageTemplateDetailResponse', MessageTemplateSerializer())),
    create=extend_schema(request=TemplateWriteSerializer, responses={201: envelope('MessageTemplateCreatedResponse', MessageTemplateSerializer())}),
    partial_update=extend_schema(request=TemplateWriteSerializer, responses=envelope('MessageTemplateUpdatedResponse', MessageTemplateSerializer())),
)
class MessageTemplateViewSet(PrivateMessagesMixin, EnvelopeResponseMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MessageTemplateSerializer
    queryset = MessageTemplate.objects.prefetch_related(Prefetch('versions',
        queryset=MessageTemplateVersion.objects.filter(number=F('template__revision')), to_attr='current_versions')).all()
    filterset_fields = ['enabled']
    search_fields = ['code', 'name']
    ordering = ['code']
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        code = 'template:update' if self.action in ('create', 'partial_update') else 'template:send' if self.action == 'send' else 'template:read'
        authorize(request, code)

    def write(self, request, identifier=None):
        with transaction.atomic():
            actor = authorize(request, 'template:update', lock=True)
            serializer = TemplateWriteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            try:
                row = save_template(request, actor, serializer.validated_data, identifier)
            except IntegrityError:
                raise ValidationError('模板编码已存在') from None
            return Response({'code': 200, 'message': 'success', 'data': MessageTemplateSerializer(row).data}, status=200 if identifier else 201)

    def create(self, request):
        return self.write(request)

    def partial_update(self, request, pk=None):
        return self.write(request, pk)

    @extend_schema(request=TemplatePreviewSerializer, responses=envelope('MessagePreviewResponse', MessagePreviewResultSerializer()))
    @action(detail=True, methods=['post'])
    def preview(self, request, pk=None):
        data = TemplatePreviewSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = self.get_object()
        if row.revision != data.validated_data['revision']:
            from apps.core.system_views import VersionConflict
            raise VersionConflict()
        subject, body = render(row.versions.get(number=row.revision), data.validated_data['values'])
        return Response({'code': 200, 'message': 'success', 'data': {'subject': subject, 'body': body}})

    @extend_schema(request=TemplateSendSerializer, responses={202: envelope('MessageSendResponse', SentDeliveriesSerializer())})
    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        data = TemplateSendSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        def callback():
            actor = authorize(request, 'template:send')
            payload = data.validated_data
            rows = submit(request, actor, pk, payload['revision'], payload['recipient_ids'], payload['channels'], payload['values'])
            return Response({'code': 200, 'message': '已登记投递，请查看结果', 'data': {'count': len(rows), 'delivery_ids': [str(row.pk) for row in rows]}}, status=202)
        return with_idempotency(request, f'message-template:{pk}:send', callback)

    @extend_schema(responses=envelope('MessageVersionsResponse', MessageVersionPageSerializer()), filters=False)
    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        rows = self.get_object().versions.all()
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(TemplateVersionSerializer(page, many=True).data)

    @extend_schema(responses=envelope('MessageChannelsResponse', ChannelsResultSerializer(many=True)), filters=False)
    @action(detail=False, methods=['get'])
    def channels(self, request):
        return Response({'code': 200, 'message': 'success', 'data': [{'key': key, 'enabled': enabled(key)} for key in CHANNELS]})

    @extend_schema(parameters=[PeopleQuerySerializer], responses=envelope('MessageRecipientsResponse', PeoplePageSerializer()), filters=False)
    @action(detail=False, methods=['get'])
    def recipients(self, request):
        return people_response(request, self)

    @extend_schema(parameters=[], responses=envelope('MessageRecipientDepartmentsResponse', PickerDepartmentsSerializer()), filters=False)
    @action(detail=False, methods=['get'], url_path='recipient-departments')
    def recipient_departments(self, request):
        return Response({'code': 200, 'message': 'success', 'data': picker_departments(request.user)})


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('MessageDeliveryDetailResponse', MessageDeliverySerializer())),
    retry=extend_schema(request=None, responses=envelope('MessageDeliveryRetryResponse', MessageDeliverySerializer())),
)
class MessageDeliveryViewSet(PrivateMessagesMixin, EnvelopeResponseMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    queryset = MessageDelivery.objects.select_related('version__template').defer('subject', 'body', 'email_binding').all()
    serializer_class = MessageDeliverySerializer
    filterset_fields = ['status', 'channel', 'recipient', 'version__template']
    ordering = ['-created_at', '-id']

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        authorize(request, 'template:send' if self.action == 'retry' else 'template:read')

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        actor = authorize(request, 'template:send')
        row = retry_delivery(request, actor, self.get_object().pk)
        return Response({'code': 200, 'message': '已登记重试', 'data': MessageDeliverySerializer(row).data})
