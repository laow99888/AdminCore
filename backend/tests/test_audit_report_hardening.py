import ipaddress
import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.exceptions import Throttled

from apps.auth_app import login_captcha, recovery
from apps.auth_app.models import User
from apps.core.models import Tenant
from apps.core.tenancy import tenant_context
from apps.data_io.models import BusinessExportRequest
from apps.files.antivirus import ScanRejected
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.tasks.models import TaskRecord
from tests.clamd_fixture import clamd_fixture


@pytest.mark.django_db
def test_legacy_authorization_repair_previews_and_is_idempotent(settings):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    tenant = Tenant.objects.create(slug='repair', name='Repair')
    other = Tenant.objects.create(slug='repair-other', name='Other')
    user = User.objects.create_user('repair-user')
    with tenant_context(tenant.pk):
        role = Role.objects.create(name='Legacy')
        permission = Permission.objects.create(name='Read', code='repair:read', resource='repair', action='read')
    RolePermission.all_objects.bulk_create([RolePermission(role=role, permission=permission)])
    UserRole.all_objects.bulk_create([UserRole(role=role, user=user)])
    conflicting = Role.all_objects.create(name='Conflict', tenant_id=other.pk)
    mismatch = UserRole.all_objects.create(user=user, role=conflicting, tenant_id=tenant.pk)

    def run(*args):
        output = StringIO()
        call_command('repair_tenant_authorization', *args, stdout=output)
        return json.loads(output.getvalue())

    with tenant_context(other.pk):
        preview = run()
        assert preview['updated'] == {'rolepermission': 1, 'userrole': 1}
        assert preview['conflicts']['userrole'] == 1
        assert UserRole.all_objects.get(role=role).tenant_id is None
        assert run('--apply')['applied']
        assert run('--apply')['updated'] == {'rolepermission': 0, 'userrole': 0}
    assert RolePermission.all_objects.get(role=role).tenant_id == tenant.pk
    assert UserRole.all_objects.get(role=role).tenant_id == tenant.pk
    mismatch.refresh_from_db()
    assert mismatch.tenant_id == tenant.pk  # 冲突只报告，不猜测、改写或删除。


def test_captcha_and_email_limits_share_trusted_proxy_identity(settings):
    settings.ADMINCORE_TRUSTED_PROXIES = (ipaddress.ip_network('10.10.0.0/16'),)
    settings.ADMINCORE_TRUSTED_PROXY_HOSTS = ()
    factory = RequestFactory()
    spoof_a = factory.get('/', REMOTE_ADDR='203.0.113.8', HTTP_X_FORWARDED_FOR='198.51.100.1')
    spoof_b = factory.get('/', REMOTE_ADDR='203.0.113.8', HTTP_X_FORWARDED_FOR='198.51.100.2')
    assert login_captcha.identities(spoof_a, 'user') == login_captcha.identities(spoof_b, 'user')
    cache.clear()
    try:
        for _ in range(20):
            recovery.limited_request(spoof_a, 'test')
        with pytest.raises(Throttled):
            recovery.limited_request(spoof_b, 'test')
        trusted_a = factory.get('/', REMOTE_ADDR='10.10.0.1', HTTP_X_FORWARDED_FOR='198.51.100.1')
        trusted_b = factory.get('/', REMOTE_ADDR='10.10.0.1', HTTP_X_FORWARDED_FOR='198.51.100.2')
        assert login_captcha.identities(trusted_a, 'user') != login_captcha.identities(trusted_b, 'user')
        recovery.limited_request(trusted_a, 'test')
        recovery.limited_request(trusted_b, 'test')
    finally:
        cache.clear()


@pytest.mark.django_db
def test_export_artifact_scans_save_and_read_and_rejects_infected_bytes(settings):
    record = TaskRecord.objects.create(name='Scan export')
    execution = BusinessExportRequest.objects.create(record=record, resource='fixture', session_version=1,
                                                     expires_at=timezone.now() + timedelta(minutes=10))
    with clamd_fixture() as (config, scans):
        settings.ADMINCORE_ANTIVIRUS = config
        execution.artifact.save('clean.csv', ContentFile(b'clean-export'))
        execution.artifact.close()
        execution.refresh_from_db()
        with execution.artifact.open('rb') as stream:
            assert stream.read() == b'clean-export'
        assert scans == [b'clean-export', b'clean-export']
        previous = execution.artifact.name
        with pytest.raises(ScanRejected):
            execution.artifact.save('bad.csv', ContentFile(b'fixture-infected'))
        assert execution.artifact.name == previous
        execution.artifact.close()
        execution.artifact.storage.delete(previous)
        execution.artifact.storage.save(previous, ContentFile(b'fixture-infected'))
        execution.refresh_from_db()
        with pytest.raises(ScanRejected):
            execution.artifact.open('rb')
