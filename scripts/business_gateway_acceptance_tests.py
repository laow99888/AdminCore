"""真实生成业务上的开放读取：独立认证、字段推断边界与整单授权。"""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.api_credentials.models import APICredential
from apps.api_credentials.authentication import digest
from apps.cg_suppliers import manifest as suppliers_manifest
from apps.cg_orders import manifest as orders_manifest
from apps.cg_suppliers.models import Supplier
from apps.permissions.models import Permission, Role, RolePermission, UserRole

pytestmark = pytest.mark.django_db
BASE = '/api/v1/api-credentials/business/'
SECRET = 'a' * 43


@pytest.fixture(autouse=True)
def enable_business(settings, monkeypatch):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'api_credentials')
    # 旧项目必须显式追加；新生成器的产物已包含声明。
    for manifest in (suppliers_manifest, orders_manifest):
        monkeypatch.setattr(manifest, 'API_CAPABILITIES', ('read',), raising=False)


def gateway(owner, scopes):
    credential = APICredential.objects.create(owner=owner, name='business-test', scopes=scopes,
        expires_at=timezone.now() + timedelta(days=1), secret_digest=digest(SECRET),
        password_digest=digest(owner.password), session_version=owner.session_version)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'ApiToken ac_{credential.pk.hex}.{SECRET}')
    return client, credential


@pytest.fixture
def supplier(admin_user):
    return Supplier.objects.create(code='GATEWAY-SUPPLIER', name='授权供应商', creator=admin_user)


def test_generated_business_read_and_no_ambient_write_authority(admin_user, admin_client, supplier):
    from apps.cg_orders.models import PurchaseOrder, PurchaseLine
    client, credential = gateway(admin_user, ['cg_suppliers:read', 'cg_orders:read'])
    url = BASE + 'cg_suppliers/records/'
    assert client.get(url).status_code == 200
    detail = client.get(url + str(supplier.pk) + '/')
    assert detail.status_code == 200 and detail.json()['data']['code'] == supplier.code
    assert detail['Cache-Control'] == 'private, no-store'
    for suffix in ('', str(supplier.pk) + '/', 'choices/', str(supplier.pk) + '/submit/'):
        assert client.post(url + suffix, {'version': 0}, format='json').status_code in {403, 404, 405}
    assert admin_client.get(url).status_code == 401
    assert client.get('/api/v1/cg-suppliers/records/').status_code == 401
    assert client.get(BASE + 'users/records/').status_code == 404
    assert client.get(BASE + 'cg_orders/records/?unknown=x').status_code == 400
    row = PurchaseOrder.objects.create(code='GATEWAY-ORDER', supplier=supplier, creator=admin_user)
    PurchaseLine.objects.create(parent=row, product='授权明细', quantity=1, price='2.00')
    order = client.get(BASE + f'cg_orders/records/{row.pk}/')
    assert order.status_code == 200, order.content
    assert order.json()['data']['lines'][0]['product'] == '授权明细'
    assert client.get(url + str(supplier.pk) + '/?model=users.User').status_code == 400
    credential.revoked_at = timezone.now()
    credential.save(update_fields=['revoked_at'])
    assert client.get(url).status_code == 401


def test_business_scope_field_read_inference_and_current_data_range(member_user, admin_user):
    role = Role.objects.create(name='gateway-role', field_permissions={'cg_suppliers': {'read': ['code'], 'write': []}})
    UserRole.objects.create(user=member_user, role=role)
    permission, _ = Permission.objects.get_or_create(code='cg_suppliers:read', defaults={
        'name': '供应商读取', 'resource': 'cg_suppliers', 'action': 'read'})
    RolePermission.objects.create(role=role, permission=permission)
    own = Supplier.objects.create(code='GW-SELF', name='敏感名称', creator=member_user)
    other = Supplier.objects.create(code='GW-OTHER', name='敏感他人', creator=admin_user)
    client, _ = gateway(member_user, ['cg_suppliers:read'])
    url = BASE + 'cg_suppliers/records/'
    result = client.get(url)
    assert result.status_code == 200, result.content
    assert [row['id'] for row in result.json()['data']['items']] == [str(own.pk)]
    assert '敏感' not in result.content.decode()
    assert client.get(url + str(other.pk) + '/').status_code == 404
    assert client.get(url + '?name=敏感').status_code == 403
    assert client.get(url + '?search=敏感').status_code == 403
    assert client.get(url + '?ordering=name').status_code in {400, 403}
    assert client.get(BASE + 'cg_orders/records/').status_code == 403
    role.field_permissions = {'cg_suppliers': {'read': ['name'], 'write': []}}
    role.save()
    refreshed = client.get(url + str(own.pk) + '/').json()['data']
    assert refreshed['name'] == '敏感名称' and 'code' not in refreshed
    RolePermission.objects.filter(role=role).delete()
    assert client.get(url).status_code == 403


def test_business_scope_registration_disabled_module_and_malformed_declarations(admin_user, monkeypatch, settings):
    client, _ = gateway(admin_user, ['cg_suppliers:read'])
    url = BASE + 'cg_suppliers/records/'
    for value in (None, ['read'], ('read', 'write'), ('*',)):
        monkeypatch.setattr(suppliers_manifest, 'API_CAPABILITIES', value)
        assert client.get(url).status_code == 404
    monkeypatch.setattr(suppliers_manifest, 'API_CAPABILITIES', ('read',))
    assert client.get(url).status_code == 200
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'cg_suppliers')
    assert client.get(url).status_code == 404


def test_independent_machine_business_fields_and_scope_are_rechecked(admin_user, admin_client):
    from apps.api_credentials.models import ServiceIdentity
    from apps.core.models import DataScopeGrant
    role = Role.objects.create(name='independent-business-reader',
        field_permissions={'cg_suppliers': {'read': ['code'], 'write': []}})
    permission, _ = Permission.objects.get_or_create(code='cg_suppliers:read', defaults={
        'name': '供应商读取', 'resource': 'cg_suppliers', 'action': 'read'})
    RolePermission.objects.create(role=role, permission=permission)
    grant = DataScopeGrant.objects.create(role=role, resource='cg_suppliers', scope='self')
    base = '/api/v1/api-credentials/service-identities/'
    created = admin_client.post(base, {'name': '业务机器', 'role_ids': [str(role.pk)],
        'current_password': 'Admin#12345'}, format='json')
    assert created.status_code == 201, created.content
    machine = ServiceIdentity.objects.select_related('user').get(pk=created.json()['data']['id'])
    issued = admin_client.post(base + f'{machine.pk}/issue/', {'name': '供应商只读',
        'scopes': ['cg_suppliers:read'], 'expires_at': (timezone.now() + timedelta(days=1)).isoformat(),
        'current_password': 'Admin#12345'}, format='json')
    assert issued.status_code == 201, issued.content
    client = APIClient(HTTP_AUTHORIZATION='ApiToken ' + issued.json()['data']['token'])
    own = Supplier.objects.create(code='MACHINE-SELF', name='机器敏感名称', creator=machine.user)
    other = Supplier.objects.create(code='MACHINE-FOREIGN', name='他人敏感名称', creator=admin_user)
    url = BASE + 'cg_suppliers/records/'
    response = client.get(url)
    assert response.status_code == 200, response.content
    assert [value['id'] for value in response.json()['data']['items']] == [str(own.pk)]
    assert '敏感' not in response.content.decode()
    assert client.get(url + str(other.pk) + '/').status_code == 404
    assert client.get(url + '?name=机器敏感名称').status_code == 403
    role.field_permissions = {'cg_suppliers': {'read': ['name'], 'write': []}}
    role.save()
    detail = client.get(url + str(own.pk) + '/')
    assert detail.status_code == 200, detail.content
    assert detail.json()['data']['name'] == '机器敏感名称' and 'code' not in detail.json()['data']
    grant.scope = 'all'; grant.save()
    assert client.get(url + str(other.pk) + '/').status_code == 200
    grant.scope = 'self'; grant.save()
    assert client.get(url + str(other.pk) + '/').status_code == 404
