"""审批关联迁移默认关闭，不改变旧表单和记录。"""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_approval_migration_keeps_legacy_records_unsubmitted():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old = [node for node in latest if node[0] != 'online_forms'] + [('online_forms', '0003_attachment_references')]
    try:
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        user = apps.get_model('auth_app', 'User').objects.create(username='legacy-form-approval')
        definition = {'fields': [{'key': 'title', 'label': '旧说明', 'type': 'text', 'required': False}]}
        form = apps.get_model('online_forms', 'OnlineForm').objects.create(
            name='历史审批迁移', code='legacy-approval', status='archived', version=4,
            definition=definition, created_by=user)
        row = apps.get_model('online_forms', 'OnlineFormRecord').objects.create(
            form=form, form_version=4, owner=user, data={'title': '保留旧记录'}, version=7,
            definition_snapshot=definition)
        MigrationExecutor(connection).migrate(latest)
        from apps.online_forms.models import OnlineForm, OnlineFormRecord
        current = OnlineFormRecord.objects.get(pk=row.pk)
        release = OnlineForm.objects.get(pk=form.pk)
        assert current.data == {'title': '保留旧记录'} and current.definition_snapshot == definition
        assert current.version == 7 and current.form_version == 4
        assert current.approval_status == 'draft' and current.approval_request_id is None
        assert release.approval_flow_code == '' and release.approval_flow_id is None and release.approval_flow_version is None
    finally:
        MigrationExecutor(connection).migrate(latest)
