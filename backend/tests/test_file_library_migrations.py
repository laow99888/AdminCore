import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_file_library_upgrade_keeps_existing_file_keys_and_acl():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old = [('files', '0009_fileaccessgrant')]
    try:
        executor.migrate(old)
        # 只回退目标 app；其余应用仍处于实际已应用版本，历史模型必须与整库一致。
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
        user = apps.get_model('auth_app', 'User').objects.create(username='legacy-file-library')
        file = apps.get_model('files', 'FileModel').objects.create(original_name='旧合同', file='legacy/keep.txt', size=123,
            uploader_id=user.pk, lifecycle_version=7)
        grant = apps.get_model('files', 'FileAccessGrant').objects.create(file_id=file.pk, user_id=user.pk)
        MigrationExecutor(connection).migrate(latest)
        from apps.files.models import FileAccessGrant, FileModel, FileFolder, FileOrganization, FileCapacity, FileDocument, FileRevision
        restored = FileModel.objects.get(pk=file.pk)
        assert restored.file.name == 'legacy/keep.txt' and restored.size == 123 and restored.lifecycle_version == 7
        assert FileAccessGrant.objects.get(pk=grant.pk).file_id == file.pk
        assert not FileFolder.objects.exists() and not FileOrganization.objects.exists()
        assert not FileDocument.objects.exists() and not FileRevision.objects.exists()
        assert not FileCapacity.all_objects.exists()
        from apps.files.capacity import capacity_data
        assert capacity_data(user.pk, None) == {
            'used_bytes': 123, 'limit_bytes': 0, 'remaining_bytes': None, 'version': 0}
    finally:
        MigrationExecutor(connection).migrate(latest)
