from drf_spectacular.utils import extend_schema, OpenApiTypes
from django.http import HttpResponse
from django.db import transaction
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.core.idempotency import with_idempotency
from apps.core.schema import envelope, MessageResponse
from . import office_preview as service


class OfficeSubmitSerializer(serializers.Serializer):
    lifecycle_version = serializers.IntegerField(min_value=1)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) != {'lifecycle_version'}:
            raise serializers.ValidationError('仅允许当前文件版本')
        return super().to_internal_value(data)


class OfficeStatusSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    error = serializers.CharField()
    expires_at = serializers.DateTimeField()


def response(job, status=200):
    result = Response({'code': status, 'message': 'success', 'data': {
        'id': str(job.pk), 'status': job.record.status, 'error': job.record.error,
        'expires_at': job.expires_at.isoformat()}}, status=status)
    result['Cache-Control'] = 'private, no-store'
    return result


class OfficeConfigView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=envelope('OfficePreviewConfiguration'))
    def get(self, request):
        result = Response({'code': 200, 'message': 'success', 'data': {
            'enabled': service.available(), 'formats': list(service.FORMATS),
            'max_bytes': service.MAX_BYTES, 'retention_seconds': service.TTL_SECONDS}})
        result['Cache-Control'] = 'private, no-store'
        return result


class OfficeSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=OfficeSubmitSerializer, responses={202: envelope('OfficePreviewSubmitted', OfficeStatusSerializer()), 409: MessageResponse})
    @transaction.atomic
    def post(self, request, file_id):
        service.require_available()
        serializer = OfficeSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.headers.get('Idempotency-Key'):
            raise serializers.ValidationError('Office 预览必须携带 Idempotency-Key')
        # Idempotency replay must recheck source ownership/session/permission too.
        from django.contrib.auth import get_user_model
        from apps.auth_app.sessions import locked_request_session
        from rest_framework.exceptions import AuthenticationFailed
        from apps.permissions.permissions import has_permission_code
        actor = get_user_model().objects.select_for_update().filter(pk=request.user.pk).first()
        if actor is None or not actor.is_active:
            raise AuthenticationFailed('登录凭据已撤销，请重新登录')
        locked_request_session(request, actor)
        request.user = actor
        if actor.must_change_password or not has_permission_code(actor, 'file:download'):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied()
        if not service.scoped_files(actor).select_for_update().filter(pk=file_id,
                lifecycle_version=serializer.validated_data['lifecycle_version']).exists():
            from rest_framework.exceptions import NotFound
            raise NotFound()
        return with_idempotency(request, 'file:office-preview:' + str(file_id),
            lambda: response(service.submit(request, file_id, serializer.validated_data['lifecycle_version']), 202))


class OfficeJobView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=envelope('OfficePreviewStatus', OfficeStatusSerializer()))
    def get(self, request, job_id):
        return response(service.get_job(request, job_id))

    @extend_schema(request=None, responses=envelope('OfficePreviewCancelled', OfficeStatusSerializer()))
    def delete(self, request, job_id):
        return response(service.get_job(request, job_id, cancel=True))


class OfficePdfView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={(200, 'application/pdf'): OpenApiTypes.BINARY, 409: MessageResponse, 410: MessageResponse})
    def get(self, request, job_id):
        content = service.get_job(request, job_id, pdf=True)
        result = HttpResponse(content, content_type='application/pdf')
        result['Content-Disposition'] = 'inline; filename="preview.pdf"'
        result['Content-Length'] = str(len(content))
        result['Cache-Control'] = 'private, no-store'
        result['X-Content-Type-Options'] = 'nosniff'
        result['Content-Security-Policy'] = "sandbox; default-src 'none'; frame-ancestors 'none'"
        result['X-Frame-Options'] = 'DENY'
        return result
