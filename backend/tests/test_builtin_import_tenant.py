import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.core.models import Post, Tenant
from apps.core.tenancy import tenant_context, current_tenant_id
from apps.data_io.tasks import run_data_import
from apps.permissions.models import Role
from apps.tasks.models import TaskRecord


@pytest.mark.django_db
@pytest.mark.parametrize('closed', [False, True])
@pytest.mark.parametrize('resource,model,content', [
    ('roles', Role, b'name,description\naudit-tenant-role,description\n'),
    ('posts', Post, b'code,name,description\naudit_post,audit-tenant-role,description\n'),
])
def test_worker_restores_and_checks_tenant_for_builtin_role_import(admin_user, settings, closed, resource, model, content):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    tenant = Tenant.objects.create(name='Audit tenant', slug='audit-import-tenant')
    client = APIClient()
    client.force_authenticate(admin_user)
    with tenant_context(tenant.pk):
        response = client.post('/api/v1/data-io/import/', {'resource': resource,
            'file': SimpleUploadedFile('source.csv', content)}, format='multipart')
        assert response.status_code == 200, response.data
        record = TaskRecord.objects.get(pk=response.data['data']['id'])
        assert record.tenant_id == tenant.pk
        assert record.import_execution.batch.tenant_id == tenant.pk
    assert current_tenant_id() is None
    if closed:
        Tenant.objects.filter(pk=tenant.pk).update(status='closed')
    run_data_import(str(record.pk))
    record.refresh_from_db()
    if closed:
        assert record.status == 'failed'
        assert not model.all_objects.filter(name='audit-tenant-role').exists()
    else:
        imported = model.all_objects.get(name='audit-tenant-role')
        assert record.status == 'success', record.result
        assert imported.tenant_id == tenant.pk
