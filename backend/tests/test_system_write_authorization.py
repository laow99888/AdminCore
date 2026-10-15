"""配置、字典与计划写入不能沿用入口旧身份。"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.core.models import DataDictionary, SystemConfig
from apps.tasks.schedule_views import schedule_row

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('operation', ['config', 'dictionary_create', 'dictionary_update', 'schedule'])
@pytest.mark.parametrize('change', ['staff', 'device'])
def test_system_writes_recheck_current_actor_and_original_device(admin_user, operation, change):
    from rest_framework.exceptions import AuthenticationFailed
    from apps.auth_app.sessions import issue_session
    dictionary = DataDictionary.objects.create(code='fixture', name='before')
    client = APIClient()
    if change == 'staff':
        client.force_authenticate(admin_user)
        get_user_model().objects.filter(pk=admin_user.pk).update(is_staff=False, is_superuser=False)
    else:
        token = issue_session(admin_user)
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))

    def write():
        if operation == 'config':
            return client.patch('/api/v1/system/config/brand.name/', {'version': 0, 'value': 'forbidden'}, format='json')
        if operation == 'dictionary_create':
            return client.post('/api/v1/system/dictionaries/', {'code': 'blocked', 'name': 'forbidden', 'version': 0, 'items': []}, format='json')
        if operation == 'dictionary_update':
            return client.patch('/api/v1/system/dictionaries/' + str(dictionary.pk) + '/', {'name': 'forbidden', 'version': 1}, format='json')
        row = schedule_row('notifications', admin_user)
        return client.patch('/api/v1/tasks/schedules/notifications/', {
            'revision': row['revision'], 'enabled': False, 'minute': '0', 'hour': '1',
            'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*',
            'timezone': 'Asia/Shanghai', 'options': {}}, format='json')

    if change == 'device':
        with patch('apps.auth_app.sessions.locked_request_session', side_effect=AuthenticationFailed('revoked')) as guard:
            response = write()
        guard.assert_called_once()
        assert response.status_code == 401
    else:
        assert write().status_code == 403
    dictionary.refresh_from_db()
    assert dictionary.name == 'before' and dictionary.version == 1
    assert not DataDictionary.objects.filter(code='blocked').exists()
    assert not SystemConfig.objects.filter(key='brand.name').exists()
