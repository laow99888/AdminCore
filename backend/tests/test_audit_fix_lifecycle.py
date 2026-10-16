"""集中修复：凭据永久撤销、显式运行环境及响应契约。"""
import os
from pathlib import Path
import subprocess
import sys

import pytest
from django.db import transaction
from rest_framework.test import APIClient

from apps.auth_app.models import AuthSession, User
from tests.test_review_regressions import credentials


@pytest.mark.django_db
@pytest.mark.parametrize('entry', ['single', 'bulk', 'model'])
def test_disabled_credentials_never_revive(admin_client, member_user, entry):
    client, tokens = credentials(member_user, 'Member#12345')
    initial = member_user.session_version
    for active in [False, True]:
        if entry == 'single':
            member_user.refresh_from_db()
            response = admin_client.patch(f'/api/v1/users/{member_user.pk}/',
                {'is_active': active, 'version': member_user.profile_version}, format='json')
            assert response.status_code == 200
        elif entry == 'bulk':
            response = admin_client.post('/api/v1/users/bulk_action/',
                {'action': 'activate' if active else 'deactivate', 'user_ids': [str(member_user.pk)]}, format='json')
            assert response.status_code == 200
        else:
            member_user.is_active = active
            member_user.save(update_fields=['is_active'])
        assert client.get('/api/v1/auth/me/').status_code == 401
    member_user.refresh_from_db()
    assert member_user.session_version == initial + 1
    assert not AuthSession.objects.filter(user=member_user, revoked_at__isnull=True).exists()
    assert APIClient().post('/api/v1/auth/refresh/', {'refresh': tokens['refresh']}, format='json').status_code == 400
    fresh, _ = credentials(member_user, 'Member#12345')
    assert fresh.get('/api/v1/auth/me/').status_code == 200


@pytest.mark.django_db
def test_disable_rollback_keeps_valid_session(member_user):
    client, _ = credentials(member_user, 'Member#12345')
    with pytest.raises(RuntimeError), transaction.atomic():
        member_user.is_active = False
        member_user.save()
        raise RuntimeError('rollback')
    assert client.get('/api/v1/auth/me/').status_code == 200


@pytest.mark.django_db
def test_stale_model_cannot_restore_credential_version(member_user):
    stale = User.objects.get(pk=member_user.pk)
    member_user.is_active = False
    member_user.save()
    stale.first_name = 'changed'
    stale.save()
    stale.refresh_from_db()
    assert stale.session_version == 1


@pytest.mark.parametrize('environment,valid', [
    (None, False), ('', False), ('prodution', False), (' production ', False),
    ('development', True), ('testing', True), ('production', True),
])
def test_settings_require_known_explicit_environment(environment, valid):
    env = {key: value for key, value in os.environ.items() if key not in
           {'DJANGO_ENV', 'DJANGO_SETTINGS_MODULE', 'ADMINCORE_PRESET', 'ADMINCORE_MODULES'}}
    env.update(PYTHON_DOTENV_DISABLED='1', DJANGO_SECRET_KEY='isolated-config-test-abcDEF0123456789_!-' * 3,
               DB_PASSWORD='isolated-config-database-secret-012345')
    if environment is not None:
        env['DJANGO_ENV'] = environment
    result = subprocess.run([sys.executable, '-c', 'import config.settings'],
        cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, timeout=20)
    assert (result.returncode == 0) == valid, result.stderr.decode(errors='replace')
