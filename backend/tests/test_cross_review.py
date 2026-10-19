"""Independent audit checks for AdminCore fbcb9638.

Run from backend with its locked Python environment:
python -m pytest -c pytest.ini /absolute/path/test_review_regressions.py -vv -s
These tests assert the desired security/functional behavior, so failures are
expected on the reviewed commit. All credentials/data below are synthetic.
"""
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from rest_framework.test import APIClient

from apps.core.tenancy import clear_current_tenant

pytestmark = pytest.mark.django_db
PASSWORD = 'AuditOnly#93842'


@pytest.fixture(autouse=True)
def isolated_state():
    cache.clear()
    clear_current_tenant()
    yield
    cache.clear()
    clear_current_tenant()


def account(username, admin=False):
    method = get_user_model().objects.create_superuser if admin else get_user_model().objects.create_user
    return method(username=username, password=PASSWORD)


def api_login(user):
    client = APIClient()
    response = client.post('/api/v1/auth/login/', {
        'username': user.username, 'password': PASSWORD,
    }, format='json')
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.json()['access'])
    return client


def browser_login(browser, username, password):
    page = browser.get('/admin/login/')
    assert page.status_code == 200
    return browser.post('/admin/login/', {
        'username': username, 'password': password, 'next': '/admin/',
        'csrfmiddlewaretoken': browser.cookies['csrftoken'].value,
    })


def test_admin_login_must_share_api_failure_budget():
    """Real CSRF-enabled admin form remains usable after API throttle."""
    from apps.logs.models import LoginLog
    user = account('audit-admin-throttle', admin=True)
    api = APIClient()
    responses = [api.post('/api/v1/auth/login/', {
        'username': user.username, 'password': 'wrong-password',
    }, format='json').status_code for _ in range(6)]
    assert responses[-1] == 429, responses
    browser = Client(enforce_csrf_checks=True)
    admin_failures = [browser_login(browser, user.username, 'wrong-password').status_code
                      for _ in range(12)]
    accepted = browser_login(browser, user.username, PASSWORD)
    reachable = browser.get('/admin/').status_code
    print({'api_attempts': responses, 'admin_wrong_attempts': admin_failures,
           'admin_correct_attempt': accepted.status_code, 'admin_page': reachable,
           'recorded_login_failures': LoginLog.objects.filter(status='failed').count()})
    assert accepted.status_code != 302, 'Admin login bypassed the API account/IP failure budget'


def test_revoke_all_devices_must_revoke_django_admin_cookie():
    from apps.permissions.models import Role
    target = account('audit-revoked-admin', admin=True)
    operator = account('audit-revoking-admin', admin=True)
    target_api = api_login(target)
    operator_api = api_login(operator)
    browser = Client(enforce_csrf_checks=True)
    assert browser_login(browser, target.username, PASSWORD).status_code == 302
    assert browser.get('/admin/').status_code == 200
    response = operator_api.post(f'/api/v1/auth/online-users/{target.pk}/revoke/',
                                 {'current_password': PASSWORD}, format='json')
    assert response.status_code == 200, response.content
    jwt_status = target_api.get('/api/v1/auth/me/').status_code
    admin_status = browser.get('/admin/').status_code
    write = browser.post('/admin/permissions/role/add/', {
        'name': 'audit-created-after-revocation', 'description': '', 'is_active': 'on', '_save': 'Save',
        'permissions-TOTAL_FORMS': '0', 'permissions-INITIAL_FORMS': '0',
        'permissions-MIN_NUM_FORMS': '0', 'permissions-MAX_NUM_FORMS': '1000',
        'csrfmiddlewaretoken': browser.cookies['csrftoken'].value,
    })
    created = Role.objects.filter(name='audit-created-after-revocation').exists()
    print({'revoke_response': response.json(), 'jwt_after_revoke': jwt_status,
           'admin_cookie_after_revoke': admin_status, 'admin_write_after_revoke': write.status_code,
           'role_created_after_revoke': created})
    assert jwt_status == 401
    assert not created, 'Revoked administrator can still create roles using the old Django cookie'
    assert admin_status != 200, 'Previously issued Django admin cookie survived all-device revocation'


@pytest.mark.parametrize('header', ['x-admincore-tenant', 'x-chunk-sha256'])
def test_cors_preflight_must_allow_application_headers(header):
    client = Client()
    response = client.options('/api/v1/files/', HTTP_ORIGIN='http://localhost:5173',
        HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type,' + header)
    allowed = [value.strip().lower() for value in response.get('Access-Control-Allow-Headers', '').split(',')]
    assert response['Access-Control-Allow-Origin'] == 'http://localhost:5173'
    print({'requested_header': header, 'status': response.status_code, 'allowed_headers': allowed})
    assert header in allowed, 'A browser blocks the actual cross-origin request'


def test_same_idempotency_key_in_two_tenants_must_not_raise_500(settings):
    from apps.core.models import Tenant, TenantMembership
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    user = account('audit-two-tenants')
    approver = account('audit-approver', admin=True)
    tenants = [Tenant.objects.create(slug='audit-a', name='Audit A'),
               Tenant.objects.create(slug='audit-b', name='Audit B')]
    for tenant in tenants:
        for member in (user, approver):
            TenantMembership.objects.create(tenant=tenant, user=member)
    client = api_login(user)
    client.raise_request_exception = False
    payload = {'title': 'Synthetic approval', 'request_type': 'other',
               'content': 'Synthetic content', 'assignee_id': str(approver.pk)}
    statuses = [client.post('/api/v1/approvals/', payload, format='json',
        HTTP_X_ADMINCORE_TENANT=str(tenant.pk),
        HTTP_IDEMPOTENCY_KEY='audit-same-key').status_code for tenant in tenants]
    print({'two_tenant_create_statuses': statuses})
    assert statuses[0] == 201, statuses
    assert statuses[1] == 201, 'Each tenant owns an independent idempotency namespace'


@pytest.mark.parametrize('model_path,field,extra', [
    ('permissions.Role', 'name', {}), ('core.DataDictionary', 'code', {}), ('core.Post', 'code', {}),
    ('notifications.MessageTemplate', 'code', {}), ('reports.ReportDefinition', 'code', {'created_by': True}),
])
def test_business_unique_keys_are_scoped_and_null_scope_stays_unique(settings, model_path, field, extra):
    from django.apps import apps
    from django.db import IntegrityError, transaction
    from apps.core.models import Tenant
    from apps.core.tenancy import tenant_context
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    model = apps.get_model(model_path)
    values = {field: 'same-key', **({'created_by': account('report-owner')} if extra else {})}
    tenants = [Tenant.objects.create(slug='scope-a', name='A'), Tenant.objects.create(slug='scope-b', name='B'), None]
    for tenant in tenants:
        with tenant_context(tenant.pk if tenant else None):
            model.objects.create(**values)
            with pytest.raises(IntegrityError), transaction.atomic():
                model.objects.create(**values)
    assert model.all_objects.filter(**{field: 'same-key'}).count() == 3


def test_role_api_allows_same_name_across_tenants_and_rejects_duplicate(settings):
    from apps.core.models import Tenant
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    actor = account('role-tenant-admin', admin=True)
    client = api_login(actor)
    tenants = [Tenant.objects.create(slug='role-a', name='A'), Tenant.objects.create(slug='role-b', name='B')]
    for tenant in tenants:
        response = client.post('/api/v1/permissions/roles/', {'name': 'Shared role'}, format='json', HTTP_X_ADMINCORE_TENANT=str(tenant.pk))
        assert response.status_code == 201, response.content
        response = client.post('/api/v1/permissions/roles/', {'name': 'Shared role'}, format='json', HTTP_X_ADMINCORE_TENANT=str(tenant.pk))
        assert response.status_code in (400, 409), response.content


def test_missing_message_revision_does_not_break_list_or_allow_send():
    from apps.notifications.models import MessageTemplate
    from apps.notifications.message_serializers import MessageTemplateSerializer
    from apps.notifications.message_services import current_template_version
    from apps.core.system_views import VersionConflict
    row = MessageTemplate.objects.create(code='missing-revision', name='Broken legacy row')
    assert MessageTemplateSerializer(row).data['current'] is None
    row.current_versions = []
    assert MessageTemplateSerializer(row).data['current'] is None
    with pytest.raises(VersionConflict):
        current_template_version(row)


def test_user_list_field_policy_queries_are_constant(django_assert_num_queries):
    from types import SimpleNamespace
    from apps.users.serializers import UserListSerializer
    actor = account('policy-reader')
    rows = [account('policy-row-' + str(i)) for i in range(10)]
    with django_assert_num_queries(1):
        assert len(UserListSerializer(rows, many=True, context={'request': SimpleNamespace(user=actor)}).data) == 10


def test_admin_failures_are_audited():
    from apps.logs.models import LoginLog
    user = account('admin-failure-audit', admin=True)
    browser = Client(enforce_csrf_checks=True)
    browser_login(browser, user.username, 'incorrect')
    assert LoginLog.objects.filter(username=user.username, status='failed').count() == 1


@pytest.mark.django_db(transaction=True)
def test_broker_publish_happens_outside_database_transaction(admin_client):
    from unittest.mock import patch
    from django.db import connection
    from django.core.files.uploadedfile import SimpleUploadedFile
    from apps.core.tasks import dispatch_outbox
    from apps.data_io.tasks import run_data_import
    with patch.object(dispatch_outbox, 'delay'):
        response = admin_client.post('/api/v1/data-io/import/', {'resource': 'users',
            'file': SimpleUploadedFile('users.csv', b'username,email\nqueued,queued@example.com\n')}, format='multipart')
    assert response.status_code == 200
    def check_publish(**kwargs):
        assert not connection.in_atomic_block, 'broker I/O must not hold database transactions'
    with patch.object(run_data_import, 'apply_async', side_effect=check_publish) as publish:
        result = dispatch_outbox()
    publish.assert_called_once()
    assert result['processed'] == 1


def test_shared_online_form_values_contract():
    import json
    from pathlib import Path
    from apps.online_forms.validators import validate_definition, validate_record
    fixture = json.loads((Path(__file__).parents[2] / 'contracts/online-form-values.json').read_text(encoding='utf-8'))
    definition = validate_definition(fixture['definition'])
    for row in fixture['cases']:
        assert validate_record(definition, row['input']) == validate_record(definition, row['submission']), row['name']


def test_actual_unique_violation_maps_to_sanitized_conflict():
    from django.db import IntegrityError, transaction
    from apps.permissions.models import Role
    from apps.core.exceptions import APIError, custom_exception_handler
    Role.objects.create(name='private-unique-value')
    try:
        with transaction.atomic():
            Role.objects.create(name='private-unique-value')
    except IntegrityError as error:
        response = custom_exception_handler(error, {})
    else:
        pytest.fail('unique constraint missing')
    assert response.status_code == 409
    assert 'private-unique-value' not in str(response.data)
    assert str(APIError().detail) == APIError.default_detail
