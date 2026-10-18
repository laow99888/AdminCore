"""查询方案表的存量升级不修改旧组织或配置数据。"""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_saved_view_migration_preserves_old_config_and_departments():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old = [('core', '0013_department_leader_organizationappointment')]
    try:
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        config = apps.get_model('core', 'SystemConfig').objects.create(key='legacy.list.config', value={'keep': True}, version=7)
        department = apps.get_model('core', 'Department').objects.create(name='历史部门', version=3)
        MigrationExecutor(connection).migrate(latest)
        from apps.core.models import SystemConfig, Department, SavedListView
        assert SystemConfig.objects.get(pk=config.pk).value == {'keep': True}
        assert SystemConfig.objects.get(pk=config.pk).version == 7
        assert Department.objects.get(pk=department.pk).version == 3
        assert SavedListView.objects.count() == 0
    finally:
        MigrationExecutor(connection).migrate(latest)
