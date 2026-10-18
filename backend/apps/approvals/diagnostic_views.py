"""Tenant-scoped bounded health scans and request diagnostics."""
from uuid import UUID

from django.utils import timezone
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework import serializers

from .diagnostics import diagnose
from .models import ApprovalRequest


class DiagnosticIssueSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.ChoiceField(choices=['warning', 'blocked'])
    node = serializers.CharField(allow_blank=True)
    step_id = serializers.UUIDField(allow_null=True)
    step_version = serializers.IntegerField(allow_null=True)


class ApprovalDiagnosticSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    workflow_version = serializers.IntegerField()
    checked_at = serializers.DateTimeField()
    scope = serializers.ChoiceField(choices=['current_and_future', 'current'])
    blocked = serializers.BooleanField()
    issues = DiagnosticIssueSerializer(many=True)


class ApprovalHealthSerializer(serializers.Serializer):
    checked_at = serializers.DateTimeField()
    scanned = serializers.IntegerField()
    next_cursor = serializers.UUIDField(allow_null=True)
    items = ApprovalDiagnosticSerializer(many=True)


class ApprovalHealthQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=100, default=25)
    cursor = serializers.UUIDField(required=False)


def tenant_required():
    from apps.core.tenancy import enabled, current_tenant_id
    if enabled() and not current_tenant_id():
        raise PermissionDenied('请先选择租户后操作审批')


def admin_required(request):
    tenant_required()
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied()


def result(application, *, future=True):
    issues = diagnose(application, future=future)
    return {'request_id': str(application.pk), 'workflow_version': application.workflow_version,
            'checked_at': timezone.now(), 'scope': 'current_and_future' if future else 'current',
            'blocked': any(row['severity'] == 'blocked' for row in issues), 'issues': issues}


def response(data):
    return Response({'code': 200, 'message': 'success', 'data': data}, headers={'Cache-Control': 'private, no-store'})


def health(request):
    admin_required(request)
    if set(request.query_params) - {'cursor', 'limit'} or any(len(values) != 1 for _, values in request.query_params.lists()):
        raise ValidationError('诊断参数无效')
    limit = request.query_params.get('limit', '25')
    if len(limit) > 3 or not limit.isascii() or not limit.isdecimal() or not 1 <= int(limit) <= 100:
        raise ValidationError('诊断批量范围为1至100')
    rows = ApprovalRequest.objects.filter(status='pending').select_related('flow').order_by('pk')
    if 'cursor' in request.query_params:
        try:
            rows = rows.filter(pk__gt=UUID(request.query_params['cursor']))
        except (ValueError, AttributeError):
            raise ValidationError('诊断游标无效') from None
    identifiers = list(rows.values_list('pk', flat=True)[:int(limit) + 1])
    selected = identifiers[:int(limit)]
    items = []
    for identifier in selected:
        # Each observation shares the decision lock; never hold a whole batch of request locks.
        with transaction.atomic():
            application = ApprovalRequest.objects.select_related('flow').select_for_update(of=('self',)).filter(pk=identifier).first()
            if application is not None:
                items.append(result(application, future=False))
    return response({'checked_at': timezone.now(), 'scanned': len(selected),
                     'next_cursor': str(selected[-1]) if len(identifiers) > int(limit) else None,
                     'items': [item for item in items if item['issues']]})
