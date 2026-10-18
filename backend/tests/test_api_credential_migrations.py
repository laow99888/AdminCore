"""真实迁移历史数据，再通过当前认证入口检查旧凭证兼容性。"""
from datetime import timedelta
import secrets

import pytest
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.api_credentials.authentication import digest
from tests.test_api_credentials import (BASE, PASSWORD, enable_api_credentials,
                                        token_client)  # noqa: F401


@pytest.mark.django_db(transaction=True)
def test_initial_credentials_upgrade_keeps_old_secret_and_starts_new_statistics():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    # 保留其他应用的当前状态，只将凭证应用退回 0001。
    old = [node for node in latest if node[0] != 'api_credentials'] + [
        ('api_credentials', '0001_initial')]
    try:
        executor.migrate(old)
        historical = executor.loader.project_state(old).apps
        user = historical.get_model('auth_app', 'User').objects.create(
            username='legacy-integration', password=make_password(PASSWORD), session_version=3)
        credentials = historical.get_model('api_credentials', 'APICredential').objects
        now = timezone.now()
        legacy = []
        for state in ('active', 'revoked', 'expired'):
            secret = secrets.token_urlsafe(32)
            row = credentials.create(
                owner_id=user.pk, name='legacy-' + state, secret_digest=digest(secret),
                password_digest=digest(user.password), session_version=user.session_version,
                scopes=['task:read'], expires_at=now + timedelta(days=-1 if state == 'expired' else 1),
                revoked_at=now if state == 'revoked' else None,
                last_used_at=now - timedelta(minutes=1),
                usage_window=int(now.timestamp() // 60), usage_count=7)
            legacy.append((row, f'ac_{row.pk.hex}.{secret}'))
        migration_started = timezone.now()
        MigrationExecutor(connection).migrate(latest)
        migration_finished = timezone.now()

        from apps.api_credentials.models import APICredential, CredentialUsageDay
        from apps.core.models import DataScopeGrant
        from apps.permissions.models import Permission, Role, RolePermission, UserRole

        role = Role.objects.create(name='Legacy integration')
        UserRole.objects.create(user_id=user.pk, role=role)
        permission, _ = Permission.objects.get_or_create(code='task:read', defaults={
            'name': 'Read tasks', 'resource': 'task', 'action': 'read'})
        RolePermission.objects.create(role=role, permission=permission)
        DataScopeGrant.objects.create(role=role, resource='task', scope='self')
        assert not CredentialUsageDay.objects.exists()
        for original, _ in legacy:
            upgraded = APICredential.objects.get(pk=original.pk)
            for field in ('owner_id', 'name', 'secret_digest', 'password_digest', 'session_version',
                          'scopes', 'created_at', 'expires_at', 'revoked_at', 'last_used_at',
                          'usage_window', 'usage_count'):
                assert getattr(upgraded, field) == getattr(original, field), field
            assert upgraded.version == 1
            assert upgraded.accepted_requests == 0
            assert upgraded.rotated_at is None
            assert migration_started <= upgraded.statistics_started_at <= migration_finished

        # 旧密钥直接通过当前完整认证和行权限入口；撤销及过期状态不得被迁移复活。
        for index, (original, token) in enumerate(legacy):
            response = token_client(token).get(BASE + 'tasks/')
            assert response.status_code == (200 if index == 0 else 401)
            upgraded = APICredential.objects.get(pk=original.pk)
            assert upgraded.accepted_requests == int(index == 0)
            assert upgraded.version == 1 and upgraded.secret_digest == original.secret_digest
        active = APICredential.objects.get(pk=legacy[0][0].pk)
        assert CredentialUsageDay.objects.get(credential=active, day=active.last_used_at.date()).requests == 1
        assert CredentialUsageDay.objects.count() == 1

        fresh = APICredential.objects.create(
            owner_id=user.pk, name='fresh', secret_digest=digest(secrets.token_urlsafe(32)),
            password_digest=digest(user.password), session_version=user.session_version,
            scopes=['task:read'], expires_at=now + timedelta(days=1))
        assert fresh.version == 1 and fresh.accepted_requests == fresh.usage_count == 0
        assert fresh.usage_window == -1 and fresh.rotated_at is None
        assert fresh.statistics_started_at >= migration_finished
    finally:
        MigrationExecutor(connection).migrate(latest)
