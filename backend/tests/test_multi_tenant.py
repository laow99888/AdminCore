import pytest
from django.test import override_settings
from django.core.management import call_command
from io import StringIO
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from apps.auth_app.models import User
from apps.core.models import Tenant, TenantMembership
from apps.core.tenancy import activate_for_user, tenant_context
from apps.example.models import WorkItem
from apps.tasks.models import ImportBatch, ImportExecution, ImportRowReceipt, TaskRecord


@pytest.mark.django_db
def test_single_project_default_keeps_existing_unassigned_records_visible(settings):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = False
    user = User.objects.create_user(username='single-project', password='Strong#12345')
    row = WorkItem.objects.create(title='旧项目记录', creator=user)
    assert WorkItem.objects.filter(pk=row.pk).exists()
    assert row.tenant_id is None


@pytest.mark.django_db
@override_settings(ADMINCORE_MULTI_TENANT_ENABLED=True)
def test_tenant_context_isolates_list_and_direct_id_queries():
    user_a = User.objects.create_user(username='tenant-a', password='Strong#12345')
    user_b = User.objects.create_user(username='tenant-b', password='Strong#12345')
    tenant_a = Tenant.objects.create(slug='tenant-a', name='租户 A')
    tenant_b = Tenant.objects.create(slug='tenant-b', name='租户 B')
    TenantMembership.objects.create(tenant=tenant_a, user=user_a, role='owner')
    TenantMembership.objects.create(tenant=tenant_b, user=user_b, role='owner')
    with tenant_context(tenant_a.pk):
        own = WorkItem.objects.create(title='A 数据', creator=user_a)
    with tenant_context(tenant_b.pk):
        other = WorkItem.objects.create(title='B 数据', creator=user_b)
        assert list(WorkItem.objects.values_list('pk', flat=True)) == [other.pk]
        assert not WorkItem.objects.filter(pk=own.pk).exists()
        with pytest.raises(DjangoValidationError):
            WorkItem.objects.create(title='越界写入', creator=user_b, tenant=tenant_a)


@pytest.mark.django_db
@override_settings(ADMINCORE_MULTI_TENANT_ENABLED=True)
def test_tenant_api_rejects_direct_id_from_other_tenant():
    """租户请求头必须同时约束列表和详情，不能靠直接 ID 绕过隔离。"""
    admin = User.objects.create_superuser(username='tenant-detail-admin', password='Strong#12345')
    tenant_a = Tenant.objects.create(slug='detail-a', name='详情 A')
    tenant_b = Tenant.objects.create(slug='detail-b', name='详情 B')
    with tenant_context(tenant_a.pk):
        own = TaskRecord.objects.create(name='A 详情', creator=admin)
    with tenant_context(tenant_b.pk):
        other = TaskRecord.objects.create(name='B 详情', creator=admin)

    client = APIClient()
    client.force_authenticate(admin)
    response = client.get('/api/v1/tasks/', HTTP_X_ADMINCORE_TENANT=str(tenant_a.pk))
    assert response.status_code == 200
    assert {item['id'] for item in response.json()['data']['items']} == {str(own.pk)}
    assert client.get(
        f'/api/v1/tasks/{other.pk}/',
        HTTP_X_ADMINCORE_TENANT=str(tenant_a.pk),
    ).status_code == 404


@pytest.mark.django_db
@override_settings(ADMINCORE_MULTI_TENANT_ENABLED=True)
def test_user_requires_membership_or_explicit_tenant_header():
    user = User.objects.create_user(username='tenant-member', password='Strong#12345')
    tenant_a = Tenant.objects.create(slug='member-a', name='成员 A')
    tenant_b = Tenant.objects.create(slug='member-b', name='成员 B')
    TenantMembership.objects.create(tenant=tenant_a, user=user, role='member')
    request = type('Request', (), {'headers': {},})()
    activate_for_user(request, user)
    assert request.tenant.pk == tenant_a.pk
    TenantMembership.objects.create(tenant=tenant_b, user=user, role='member')
    with pytest.raises(ValidationError):
        activate_for_user(type('Request', (), {'headers': {}})(), user)
    tenant_c = Tenant.objects.create(slug='member-c', name='成员 C')
    with pytest.raises(PermissionDenied):
        activate_for_user(type('Request', (), {'headers': {'X-AdminCore-Tenant': str(tenant_c.pk)}})(), user)


@pytest.mark.django_db
def test_legacy_tenant_assignment_is_preview_then_explicit_apply():
    user = User.objects.create_user(username='legacy-owner', password='Strong#12345')
    row = WorkItem.objects.create(title='待归属旧数据', creator=user)
    tenant = Tenant.objects.create(slug='legacy-target', name='旧项目租户')

    preview = StringIO()
    call_command('assign_legacy_tenant', tenant='legacy-target', stdout=preview)
    row.refresh_from_db()
    assert row.tenant_id is None
    assert '仅预览' in preview.getvalue()

    call_command('assign_legacy_tenant', tenant='legacy-target', apply=True, stdout=StringIO())
    row.refresh_from_db()
    assert row.tenant_id == tenant.pk


@pytest.mark.django_db
@override_settings(ADMINCORE_MULTI_TENANT_ENABLED=True)
def test_import_execution_and_row_receipts_follow_tenant_context():
    user = User.objects.create_user(username='import-owner', password='Strong#12345')
    tenant_a = Tenant.objects.create(slug='import-a', name='导入 A')
    tenant_b = Tenant.objects.create(slug='import-b', name='导入 B')
    with tenant_context(tenant_a.pk):
        task = TaskRecord.objects.create(name='导入任务', task_type='import', creator=user)
        batch = ImportBatch.objects.create(source_sha256='a' * 64, resource='users', active_record=task)
        execution = ImportExecution.objects.create(tenant=tenant_a, record=task, batch=batch, session_version=1)
        receipt = ImportRowReceipt.objects.create(tenant=tenant_a, batch=batch, row=2, created=True)
    with tenant_context(tenant_b.pk):
        assert not ImportExecution.objects.filter(pk=execution.pk).exists()
        assert not ImportRowReceipt.objects.filter(pk=receipt.pk).exists()


@pytest.mark.django_db
@override_settings(ADMINCORE_MULTI_TENANT_ENABLED=True)
def test_tenant_api_requires_header_for_multiple_memberships_and_closes_members():
    user = User.objects.create_user(username='tenant-api', password='Strong#12345')
    tenant_a = Tenant.objects.create(slug='api-a', name='API A')
    tenant_b = Tenant.objects.create(slug='api-b', name='API B')
    TenantMembership.objects.create(tenant=tenant_a, user=user, role='member')
    TenantMembership.objects.create(tenant=tenant_b, user=user, role='member')
    client = APIClient()
    client.force_authenticate(user)

    ambiguous = client.get('/api/v1/organization/my-tenants/')
    assert ambiguous.status_code == 200
    assert {item['id'] for item in ambiguous.data['data']} == {str(tenant_a.pk), str(tenant_b.pk)}
    selected = client.get('/api/v1/organization/my-tenants/', HTTP_X_ADMINCORE_TENANT=str(tenant_a.pk))
    assert selected.status_code == 200
    assert {item['id'] for item in selected.data['data']} == {str(tenant_a.pk), str(tenant_b.pk)}

    admin = User.objects.create_superuser(username='tenant-api-admin', password='Strong#12345')
    admin_client = APIClient()
    admin_client.force_authenticate(admin)
    closed = admin_client.patch(f'/api/v1/organization/tenants/{tenant_a.pk}/', {'status': 'closed'}, format='json')
    assert closed.status_code == 200
    assert not TenantMembership.objects.get(tenant=tenant_a, user=user).is_active
    assert client.get('/api/v1/organization/my-tenants/', HTTP_X_ADMINCORE_TENANT=str(tenant_a.pk)).status_code == 403


@pytest.mark.django_db
@override_settings(ADMINCORE_MULTI_TENANT_ENABLED=True)
def test_tenant_context_is_added_to_partial_model_updates():
    user = User.objects.create_user(username='tenant-partial', password='Strong#12345')
    tenant = Tenant.objects.create(slug='partial-a', name='部分更新')
    row = WorkItem.objects.create(title='待归属', creator=user)
    with tenant_context(tenant.pk):
        row.title = '更新标题'
        row.save(update_fields=['title'])
        row.refresh_from_db()
        assert row.tenant_id == tenant.pk
