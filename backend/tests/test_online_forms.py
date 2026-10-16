import pytest
from django.contrib.auth import get_user_model

from apps.online_forms.models import OnlineForm, OnlineFormRecord
from apps.online_forms.manifest import MODULE

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'online_forms')
    settings.ROOT_URLCONF = 'tests.online_forms_urls'


def definition():
    return {'fields': [
        {'key': 'title', 'label': '标题', 'type': 'text', 'required': True, 'max_length': 20},
        {'key': 'kind', 'label': '类型', 'type': 'select', 'required': True, 'options': ['A', 'B']},
        {'key': 'amount', 'label': '金额', 'type': 'number', 'required': False, 'min': 0, 'max': 100},
    ]}


def grant_record_permissions(user):
    from apps.permissions.models import Permission, Role, RolePermission, UserRole
    role = Role.objects.create(name='online-form-' + str(user.pk))
    for resource, action, name, code in MODULE.permissions:
        permission, _ = Permission.objects.get_or_create(resource=resource, action=action, defaults={'name': name, 'code': code})
        if action in {'record_read', 'record_create', 'record_update'}:
            RolePermission.objects.create(role=role, permission=permission)
    UserRole.objects.create(user=user, role=role)


def test_design_publish_and_immutable_after_publish(admin_client):
    created = admin_client.post('/api/v1/online-forms/forms/', {'name': '申请', 'code': 'application', 'definition': definition()}, format='json')
    assert created.status_code == 201
    row = created.json()['data']
    assert admin_client.post(f"/api/v1/online-forms/forms/{row['id']}/publish/", format='json').status_code == 200
    assert admin_client.patch(f"/api/v1/online-forms/forms/{row['id']}/", {'name': '改名'}, format='json').status_code == 400


@pytest.mark.parametrize('bad', [
    {'fields': [{'key': 'x', 'label': 'X', 'type': 'text', 'html': '<script>alert(1)</script>'}]},
    {'fields': [{'key': 'x', 'label': 'X', 'type': 'unknown'}]},
    {'fields': [{'key': 'x', 'label': 'X', 'type': 'text'}, {'key': 'x', 'label': 'Y', 'type': 'text'}]},
    {'fields': [{'key': '__proto__', 'label': 'X', 'type': 'text'}]},
])
def test_malicious_or_invalid_definition_rejected(admin_client, bad):
    response = admin_client.post('/api/v1/online-forms/forms/', {'name': '坏表单', 'code': 'unsafe-form', 'definition': bad}, format='json')
    assert response.status_code == 400
    assert not OnlineForm.objects.filter(code='unsafe-form').exists()


def test_records_validate_and_are_owner_scoped(admin_client, member_client, member_user):
    grant_record_permissions(member_user)
    row = admin_client.post('/api/v1/online-forms/forms/', {'name': '申请', 'code': 'record-form', 'definition': definition()}, format='json').json()['data']
    admin_client.post(f"/api/v1/online-forms/forms/{row['id']}/publish/", format='json')
    base = '/api/v1/online-forms/record-form/records/'
    missing = member_client.post(base, {'data': {'kind': 'A'}}, format='json', HTTP_IDEMPOTENCY_KEY='record-missing')
    assert missing.status_code == 400
    created = member_client.post(base, {'data': {'title': '申请一', 'kind': 'A', 'amount': 10}}, format='json', HTTP_IDEMPOTENCY_KEY='record-1')
    assert created.status_code == 201
    replay = member_client.post(base, {'data': {'title': '申请一', 'kind': 'A', 'amount': 10}}, format='json', HTTP_IDEMPOTENCY_KEY='record-1')
    assert replay.status_code == 201 and OnlineFormRecord.objects.count() == 1
    assert member_client.post(base, {'data': {'title': '越权', 'kind': 'C'}}, format='json', HTTP_IDEMPOTENCY_KEY='record-2').status_code == 400
    other = get_user_model().objects.create_user('other-form-user', password='Other#12345')
    grant_record_permissions(other)
    from rest_framework.test import APIClient
    other_client = APIClient(); other_client.force_authenticate(other)
    assert other_client.get(base).json()['data']['pagination']['total'] == 0


def test_module_is_optional(settings, admin_client):
    settings.ADMINCORE_MODULES = tuple(item for item in settings.ADMINCORE_MODULES if item != 'online_forms')
    assert admin_client.get('/api/v1/online-forms/forms/').status_code == 404
