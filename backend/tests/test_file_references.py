from datetime import timedelta
from threading import Event
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection, connections, transaction, IntegrityError
from django.test import override_settings
from django.utils import timezone

from apps.approvals.models import ApprovalRequest, ApprovalFileReference
from apps.core.models import LifecycleConflict, Tenant
from apps.core.tenancy import tenant_context
from apps.files.models import FileModel, FileAccessGrant
from apps.files.references import is_referenced, unreferenced_files
from tests.file_permissions import grant_files

pytestmark = pytest.mark.django_db


def document(user, **extra):
    return FileModel.objects.create(original_name='合同.txt', file='reference-test/contract.txt',
        file_type='txt', size=12, uploader=user, **extra)


def pin(file, user, **extra):
    application = ApprovalRequest.objects.create(title='隐藏的合同', content='敏感', applicant=user, assignee=user,
        business_module='retired_business', business_record_id=file.pk, **extra)
    return ApprovalFileReference.objects.create(request=application, file=file, tenant_id=application.tenant_id)


def test_protected_file_cannot_be_recycled_purged_or_directly_deleted(admin_client, admin_user):
    file = document(admin_user); reference = pin(file, admin_user)
    for method, url in [('delete', f'/api/v1/files/{file.pk}/'), ('delete', f'/api/v1/files/{file.pk}/purge/')]:
        response = getattr(admin_client, method)(url)
        assert response.status_code == 409, response.content
        assert '引用' in response.json()['message']
    with pytest.raises(LifecycleConflict):
        file.soft_delete(actor=admin_user)
    with pytest.raises(LifecycleConflict):
        file.hard_delete()
    from apps.core.models import OutboxEvent
    assert not OutboxEvent.objects.filter(topic='file.purge').exists()
    file.refresh_from_db(); assert not file.is_deleted and file.lifecycle_version == 1
    assert ApprovalFileReference.objects.filter(pk=reference.pk).exists()


def test_status_is_private_does_not_disclose_business_and_does_not_grant_acl(admin_client, admin_user, member_client, member_user):
    file = document(admin_user); pin(file, admin_user)
    url = f'/api/v1/files/{file.pk}/references/'
    response = admin_client.get(url)
    assert response.status_code == 200 and response['Cache-Control'] == 'private, no-store'
    assert response.json()['data'] == {'protected': True, 'lifecycle_version': 1}
    grant_files(member_user, 'file:read', 'file:download')
    assert member_client.get(url).status_code == 404
    assert member_client.get(f'/api/v1/files/{file.pk}/download/').status_code == 404
    FileAccessGrant.objects.create(file=file, user=member_user)
    assert member_client.get(url).json()['data']['protected']
    FileAccessGrant.objects.all().update(is_active=False)
    assert member_client.get(url).status_code == 404


def test_no_reference_status_permission_is_rejected(member_client, member_user):
    file = document(member_user)
    assert member_client.get(f'/api/v1/files/{file.pk}/references/').status_code == 403


def test_removing_canonical_reference_releases_file_without_deleting_it(admin_client, admin_user):
    file = document(admin_user); reference = pin(file, admin_user)
    assert is_referenced(file)
    reference.request.delete()
    assert not is_referenced(file) and FileModel.objects.filter(pk=file.pk).exists()
    response = admin_client.delete(f'/api/v1/files/{file.pk}/')
    assert response.status_code == 204
    file.refresh_from_db(); assert file.is_deleted and file.lifecycle_version == 2


@pytest.mark.parametrize('dry_run', [True, False])
def test_recycle_batch_reports_protected_item_without_aborting_others(admin_client, admin_user, dry_run):
    file = document(admin_user, is_deleted=True, deleted_at=timezone.now()); pin(file, admin_user)
    free = document(admin_user, is_deleted=True, deleted_at=timezone.now())
    response = admin_client.post('/api/v1/files/recycle_action/', {'action': 'purge', 'dry_run': dry_run, 'confirmation': 'DELETE',
        'items': [{'id': str(row.pk), 'lifecycle_version': 1} for row in (file, free)]}, format='json')
    assert response.status_code == 200, response.content
    result = response.json()['data']
    assert result['failed'] == result['succeeded'] == 1
    assert result['results'][0]['status'] == 409
    assert FileModel.objects.filter(pk=free.pk).exists() is dry_run
    assert FileModel.objects.filter(pk=file.pk).exists()


def test_retention_preview_and_execution_skip_protected_history(admin_user):
    from apps.tasks.tasks import cleanup_soft_deleted_files
    cutoff = timezone.now() - timedelta(days=100)
    file = document(admin_user, is_deleted=True, deleted_at=cutoff); pin(file, admin_user)
    free = document(admin_user, is_deleted=True, deleted_at=cutoff)
    preview = cleanup_soft_deleted_files(dry_run=True)
    assert preview['eligible_files'] == 1 and preview['eligible_bytes'] == free.size and preview['protected_files'] == 1
    result = cleanup_soft_deleted_files()
    assert result['purged_files'] == result['protected_files'] == 1
    assert FileModel.objects.filter(pk=file.pk).exists() and not FileModel.objects.filter(pk=free.pk).exists()


def test_reference_protection_survives_disabled_approvals_and_tenant_scoping(admin_user):
    a = Tenant.objects.create(slug='ref-a', name='甲'); b = Tenant.objects.create(slug='ref-b', name='乙')
    file = document(admin_user, tenant=a); pin(file, admin_user, tenant=a)
    with override_settings(ADMINCORE_MODULES=('files',), ADMINCORE_MULTI_TENANT_ENABLED=True):
        with tenant_context(b.pk):
            assert is_referenced(file)
            assert not unreferenced_files(FileModel.all_objects.filter(pk=file.pk)).exists()


def test_references_are_unique_per_snapshot_and_file(admin_user):
    file = document(admin_user); reference = pin(file, admin_user)
    with pytest.raises(IntegrityError), transaction.atomic():
        ApprovalFileReference.objects.create(file=file, request=reference.request)


def test_active_avatar_also_requires_releasing_its_canonical_binding(admin_user):
    file = document(admin_user, purpose='avatar')
    admin_user.avatar_file = file
    admin_user.save(update_fields=['avatar_file'])
    with pytest.raises(LifecycleConflict):
        file.soft_delete(actor=admin_user)
    admin_user.avatar_file = None
    admin_user.save(update_fields=['avatar_file'])
    file.soft_delete(actor=admin_user)
    assert file.is_deleted


@pytest.mark.django_db(transaction=True)
def test_postgres_new_reference_wins_against_concurrent_soft_delete(admin_user):
    if connection.vendor != 'postgresql':
        pytest.skip('需要 PostgreSQL 行锁')
    file = document(admin_user)
    entered, attempted = Event(), Event()
    def add_reference():
        try:
            with transaction.atomic():
                locked = FileModel.objects.select_for_update().get(pk=file.pk, is_deleted=False)
                entered.set(); assert attempted.wait(10)
                pin(locked, admin_user)
        finally:
            connections.close_all()
    def remove():
        try:
            assert entered.wait(10)
            attempted.set()
            with pytest.raises(LifecycleConflict):
                FileModel.objects.get(pk=file.pk).soft_delete()
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(add_reference), pool.submit(remove)]
        for future in futures:
            future.result(timeout=20)
    file.refresh_from_db(); assert not file.is_deleted and is_referenced(file)
