"""Fresh write authorization complements optimistic versions on role/menu management."""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.logs.models import OperationLog
from apps.permissions.models import Menu, Role

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('resource,model', [('roles', Role), ('menus', Menu)])
@pytest.mark.parametrize('operation', ['create', 'update', 'delete'])
def test_request_entry_staff_cannot_write_after_revocation(admin_user, resource, model, operation):
    row = model.objects.create(name='before', **({'path': '/fixture'} if model is Menu else {}))
    client = APIClient()
    client.force_authenticate(admin_user)
    # The request object deliberately retains the previous staff flags.
    get_user_model().objects.filter(pk=admin_user.pk).update(is_staff=False, is_superuser=False)
    path = '/api/v1/permissions/' + resource + '/'
    if operation == 'create':
        response = client.post(path, {'name': 'forbidden', **({'path': '/forbidden'} if model is Menu else {})}, format='json')
    elif operation == 'update':
        response = client.patch(path + str(row.pk) + '/', {'name': 'forbidden', 'version': 1}, format='json')
    else:
        response = client.delete(path + str(row.pk) + '/')
    assert response.status_code == 403
    row.refresh_from_db()
    assert row.name == 'before' and row.version == 1
    assert not model.objects.filter(name='forbidden').exists()
    assert not OperationLog.objects.filter(resource='role' if model is Role else 'menu').exists()


@pytest.mark.parametrize('resource,model', [('roles', Role), ('menus', Menu)])
@pytest.mark.parametrize('operation', ['create', 'update', 'delete'])
def test_device_is_rechecked_before_permission_resource_write(admin_client, resource, model, operation):
    from rest_framework.exceptions import AuthenticationFailed
    row = model.objects.create(name='before', **({'path': '/fixture'} if model is Menu else {}))
    path = '/api/v1/permissions/' + resource + '/'
    with patch('apps.auth_app.sessions.locked_request_session', side_effect=AuthenticationFailed('revoked')) as check:
        if operation == 'create':
            response = admin_client.post(path, {'name': 'forbidden', **({'path': '/forbidden'} if model is Menu else {})}, format='json')
        elif operation == 'update':
            response = admin_client.patch(path + str(row.pk) + '/', {'name': 'forbidden', 'version': 1}, format='json')
        else:
            response = admin_client.delete(path + str(row.pk) + '/')
    assert response.status_code == 401
    check.assert_called_once()
    row.refresh_from_db()
    assert row.name == 'before' and row.version == 1
    assert not model.objects.filter(name='forbidden').exists()
