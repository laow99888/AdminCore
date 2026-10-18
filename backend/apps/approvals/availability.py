"""Database-side exception selection; current visits only, bounded by normal list pagination."""
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from apps.core.tenancy import enabled
from .models import ApprovalStep


def exception_queryset(rows):
    steps = ApprovalStep.objects.filter(request_id=OuterRef('pk'), status='pending', node_key=OuterRef('current_node'))
    invalid = Q(assignee__isnull=True) | Q(assignee__is_active=False) | Q(assignee__is_service_account=True) | Q(assignee__must_change_password=True)
    invalid |= Q(delegated_to__isnull=False) & (Q(delegated_to__is_active=False) | Q(delegated_to__is_service_account=True) | Q(delegated_to__must_change_password=True))
    legacy = Q(flow__isnull=True) & (Q(assignee__is_active=False) | Q(assignee__is_service_account=True) | Q(assignee__must_change_password=True))
    if enabled():
        from apps.core.models import TenantMembership
        member = TenantMembership.objects.filter(user_id=OuterRef('assignee_id'), tenant_id=OuterRef('request__tenant_id'), is_active=True, tenant__status='active')
        delegate = TenantMembership.objects.filter(user_id=OuterRef('delegated_to_id'), tenant_id=OuterRef('request__tenant_id'), is_active=True, tenant__status='active')
        steps = steps.annotate(valid_member=Exists(member), valid_delegate=Exists(delegate))
        invalid |= Q(valid_member=False) | (Q(delegated_to__isnull=False) & Q(valid_delegate=False))
        member = TenantMembership.objects.filter(user_id=OuterRef('assignee_id'), tenant_id=OuterRef('tenant_id'), is_active=True, tenant__status='active')
        rows = rows.annotate(valid_legacy_member=Exists(member))
        legacy |= Q(flow__isnull=True, valid_legacy_member=False)
    rows = rows.annotate(bad_current_step=Exists(steps.filter(invalid | Q(due_at__lte=timezone.now()))), has_current_step=Exists(steps))
    return rows.filter(status='pending').filter(legacy | Q(bad_current_step=True) | Q(flow__isnull=False, has_current_step=False))
