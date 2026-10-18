"""附件迁移不把历史文本 UUID 猜测为引用；存量记录和其他模块保持原样。"""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_attachment_migration_keeps_legacy_records_and_snapshot_unchanged():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old = [node for node in latest if node[0] != 'online_forms'] + [('online_forms', '0002_release_history')]
    try:
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        user = apps.get_model('auth_app', 'User').objects.create(username='legacy-attachment-form')
        # 看起来像文件 ID 的普通文本仍是普通文本，迁移不得扩大访问或永久保护无关文件。
        value = 'ef23a35e-6dc1-4e4f-bcb0-cf69c8f21a12'
        definition = {'fields': [{'key': 'proof', 'label': '旧说明', 'type': 'text', 'required': False}]}
        form = apps.get_model('online_forms', 'OnlineForm').objects.create(
            name='历史附件迁移', code='legacy-attachment', status='archived', version=4,
            definition=definition, created_by=user)
        row = apps.get_model('online_forms', 'OnlineFormRecord').objects.create(
            form=form, form_version=4, owner=user, data={'proof': value}, version=7,
            definition_snapshot=definition)
        MigrationExecutor(connection).migrate(latest)
        from apps.online_forms.models import OnlineFormFileReference, OnlineFormRecord
        current = OnlineFormRecord.objects.get(pk=row.pk)
        assert current.data == {'proof': value}
        assert current.definition_snapshot == definition
        assert current.version == 7 and current.form_version == 4
        assert not OnlineFormFileReference.objects.exists()
    finally:
        MigrationExecutor(connection).migrate(latest)
