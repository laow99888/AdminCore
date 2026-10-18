"""本人摘要、受控业务提醒提交与去标识运营汇总。"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth_app.write_authorization import authorize_write
from apps.core.models import OutboxEvent
from apps.core.schema import envelope
from apps.logs.audit import write_audit
from .announcement_services import authorize
from .digests import digest_references, enqueue_business_notice, reference_for, refresh_recipient, tenant_id
from .message_serializers import StrictMessageSerializer
from .message_services import candidates
from .models import BusinessNotice, MessageDelivery, Notification


class PrivateView(APIView):
    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response


class RefreshResultSerializer(serializers.Serializer):
    processed = serializers.IntegerField()
    published = serializers.IntegerField()
    suppressed = serializers.IntegerField()
    summaries = serializers.IntegerField()


class ReferenceSerializer(serializers.Serializer):
    resource = serializers.CharField()
    label = serializers.CharField()
    object_id = serializers.UUIDField()
    path = serializers.CharField()


class DigestReferenceSerializer(serializers.Serializer):
    items = ReferenceSerializer(many=True)
    authorization_checked_at = serializers.DateTimeField()


class DigestStatusSerializer(serializers.Serializer):
    pending = serializers.IntegerField()
    due = serializers.IntegerField()
    next_due_at = serializers.DateTimeField(allow_null=True)


class DigestStatusView(PrivateView):
    @extend_schema(responses=envelope('NotificationDigestStatus', DigestStatusSerializer()))
    def get(self, request):
        authorize(request)
        rows = BusinessNotice.all_objects.filter(tenant_id=tenant_id(), recipient=request.user, state='pending')
        next_due = rows.order_by('due_at').values_list('due_at', flat=True).first()
        return Response({'code': 200, 'message': 'success', 'data': {
            'pending': rows.count(), 'due': rows.filter(due_at__lte=timezone.now()).count(), 'next_due_at': next_due}})


class DigestRefreshView(PrivateView):
    @extend_schema(request=None, responses=envelope('RefreshedNotificationDigests', RefreshResultSerializer()))
    @transaction.atomic
    def post(self, request):
        actor = authorize_write(request)
        if request.data:
            raise ValidationError('摘要刷新不接受用户、租户或提前发送参数')
        counts = refresh_recipient(actor.pk, tenant_id())
        write_audit(request=request, actor=actor, resource='business_notice', identifier=actor.pk,
                    action='update', after=counts)
        return Response({'code': 200, 'message': 'success', 'data': counts})


class DigestDetailView(PrivateView):
    @extend_schema(responses=envelope('NotificationDigestReferences', DigestReferenceSerializer()))
    def get(self, request, notification_id):
        actor = authorize(request)
        return Response({'code': 200, 'message': 'success', 'data': digest_references(actor, notification_id)})


class BusinessNoticeWriteSerializer(StrictMessageSerializer):
    resource = serializers.RegexField(r'^[a-z][a-z0-9_]{0,31}$', max_length=32)
    object_id = serializers.UUIDField()
    event_id = serializers.UUIDField()
    recipient_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100)

    def validate_recipient_ids(self, values):
        if len(set(values)) != len(values):
            raise serializers.ValidationError('收件人不能重复')
        return values


class BusinessNoticeResultSerializer(serializers.Serializer):
    created = serializers.IntegerField()
    replayed = serializers.IntegerField()
    pending = serializers.IntegerField()
    published = serializers.IntegerField()
    suppressed = serializers.IntegerField()


class BusinessNoticeView(PrivateView):
    @extend_schema(request=BusinessNoticeWriteSerializer, responses=envelope('SubmittedBusinessNotices', BusinessNoticeResultSerializer()))
    @transaction.atomic
    def post(self, request):
        authorize(request, 'template:send')
        data = BusinessNoticeWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values, scope = data.validated_data, tenant_id()
        actor = authorize_write(request, 'template:send', admin=True, related_users=values['recipient_ids'])
        if reference_for(actor, values['resource'], values['object_id'], scope) is None:
            raise NotFound()
        recipients = list(candidates(actor).filter(pk__in=values['recipient_ids']).order_by('pk'))
        if len(recipients) != len(values['recipient_ids']):
            raise NotFound()
        # authorize_write 已按主键顺序锁住所有用户；不可读对象回滚整批。
        result = dict(created=0, replayed=0, pending=0, published=0, suppressed=0)
        for recipient in recipients:
            row, created = enqueue_business_notice(recipient, values['resource'], values['object_id'], str(values['event_id']))
            result['created' if created else 'replayed'] += 1
            result[row.state] += 1
        write_audit(request=request, actor=actor, resource='business_notice', identifier=values['event_id'],
                    action='create', after={'resource': values['resource'], 'count': len(recipients), **result})
        return Response({'code': 200, 'message': 'success', 'data': result})


class DeliveryStateCountSerializer(serializers.Serializer):
    channel = serializers.CharField()
    status = serializers.CharField()
    count = serializers.IntegerField()


class StateCountSerializer(serializers.Serializer):
    status = serializers.CharField()
    count = serializers.IntegerField()


class NoticeStateCountSerializer(serializers.Serializer):
    state = serializers.CharField()
    count = serializers.IntegerField()


class NotificationOperationsSerializer(serializers.Serializer):
    window_days = serializers.IntegerField()
    since = serializers.DateTimeField()
    until = serializers.DateTimeField()
    inbox_created = serializers.IntegerField()
    inbox_read = serializers.IntegerField()
    deliveries = DeliveryStateCountSerializer(many=True)
    outbox = StateCountSerializer(many=True)
    business_notices = NoticeStateCountSerializer(many=True)
    due_notices = serializers.IntegerField()
    final_delivery_receipts_supported = serializers.BooleanField()


class NotificationOperationsView(PrivateView):
    @extend_schema(parameters=[OpenApiParameter('days', int, description='默认7天；1至90天，按创建时间统计当前租户')],
                   responses=envelope('NotificationOperationsResponse', NotificationOperationsSerializer()))
    def get(self, request):
        authorize(request, 'template:read')
        params = request.query_params
        if set(params) - {'days'} or len(params.getlist('days')) > 1:
            raise ValidationError('通知统计只支持单个days参数（1至90天）')
        raw = params.get('days', '7')
        if not 1 <= len(raw) <= 2 or not raw.isascii() or not raw.isdecimal() or not 1 <= int(raw) <= 90:
            raise ValidationError('通知统计只支持单个days参数（1至90天）')
        days, now, scope = int(raw), timezone.now(), tenant_id()
        since = now - timedelta(days=days)
        window = {'tenant_id': scope, 'created_at__gte': since, 'created_at__lte': now}
        deliveries = MessageDelivery.all_objects.filter(**window)
        inbox = Notification.all_objects.filter(**window)
        outbox = OutboxEvent.all_objects.filter(**window, topic__in=['notification.created', 'notification.delivery'])
        notices = BusinessNotice.all_objects.filter(**window)
        return Response({'code': 200, 'message': 'success', 'data': {
            'window_days': days, 'since': since, 'until': now,
            'inbox_created': inbox.count(), 'inbox_read': inbox.filter(is_read=True).count(),
            'deliveries': list(deliveries.values('channel', 'status').annotate(count=Count('pk')).order_by('channel', 'status')),
            'outbox': list(outbox.values('status').annotate(count=Count('pk')).order_by('status')),
            'business_notices': list(notices.values('state').annotate(count=Count('pk')).order_by('state')),
            'due_notices': notices.filter(state='pending', due_at__lte=now).count(),
            # 当前无供应商入站送达回执；succeeded 只能解释为渠道执行完成/接口接受。
            'final_delivery_receipts_supported': False,
        }})
