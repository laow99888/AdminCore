"""旧账本升级后保留回执，新增选项不改变旧导入语义。"""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_upgrade_preserves_legacy_import_batch_and_receipt():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    # 确定实际历史叶子，避免把名称约定当作迁移事实。
    parents = executor.loader.get_migration('tasks', '0013_importbatch_options_importrowreceipt_outcome').dependencies
    old = [('data_io', None), next(item for item in parents if item[0] == 'tasks')]
    try:
        executor.migrate(old)
        state = executor.loader.project_state([old[1]]).apps
        batch = state.get_model('tasks', 'ImportBatch').objects.create(source_sha256='legacy-sha', resource='users')
        receipt = state.get_model('tasks', 'ImportRowReceipt').objects.create(batch_id=batch.pk, row=2, created=True)
        MigrationExecutor(connection).migrate(latest)
        from apps.tasks.models import ImportBatch, ImportRowReceipt
        assert ImportBatch.objects.get(pk=batch.pk).options == {}
        row = ImportRowReceipt.objects.get(pk=receipt.pk)
        assert row.created is True and row.outcome == '' and row.error == ''
    finally:
        MigrationExecutor(connection).migrate(latest)
