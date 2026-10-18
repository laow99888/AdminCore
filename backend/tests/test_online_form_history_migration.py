import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_existing_published_and_archived_records_receive_exact_frozen_definition():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old = [('online_forms', '0001_initial')]
    try:
        executor.migrate(old)
        # 只回退目标 app；其余应用仍处于实际已应用版本，历史模型必须与整库一致。
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
        user = apps.get_model('auth_app', 'User').objects.create(username='legacy-form-history')
        forms = apps.get_model('online_forms', 'OnlineForm').objects
        records = apps.get_model('online_forms', 'OnlineFormRecord').objects
        pairs = []
        for status in ('published', 'archived'):
            schema = {'fields': [{'key': status, 'label': '原始字段', 'type': 'text', 'required': True}]}
            form = forms.create(name='存量表单', code='legacy-' + status, status=status, version=7, definition=schema, created_by=user)
            record = records.create(form=form, form_version=7, owner=user, data={status: '原始数据'}, version=4)
            pairs.append((form.pk, record.pk, schema, {status: '原始数据'}))
        MigrationExecutor(connection).migrate(latest)
        from apps.online_forms.models import OnlineForm, OnlineFormRecord
        for form_id, record_id, schema, data in pairs:
            form = OnlineForm.objects.get(pk=form_id)
            record = OnlineFormRecord.objects.get(pk=record_id)
            assert form.release_number == 1 and form.version == 7
            assert record.definition_snapshot == schema and record.data == data
            assert record.form_version == 7 and record.version == 4
    finally:
        MigrationExecutor(connection).migrate(latest)
