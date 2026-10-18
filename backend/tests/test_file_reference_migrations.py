import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_legacy_snapshot_upgrade_protects_same_tenant_files_without_rewriting_data():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old = [('approvals', '0007_remove_approvalstep_unique_approval_step_assignee_and_more'),
           ('files', '0010_filefolder_fileorganization_fileorganizationtag_and_more')]
    try:
        executor.migrate(old)
        # 只回退目标 app；其余应用仍处于实际已应用版本，历史模型必须与整库一致。
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
        user = apps.get_model('auth_app', 'User').objects.create(username='legacy-reference')
        tenant = apps.get_model('core', 'Tenant').objects.create(slug='legacy-ref', name='旧租户')
        files = apps.get_model('files', 'FileModel').objects
        def file(**extra):
            return files.create(original_name='旧合同', file='legacy/unchanged.txt', lifecycle_version=7, **extra)
        main = file(); detail = file(is_deleted=True); foreign = file(tenant_id=tenant.pk)
        avatar = file(purpose='avatar'); source = file(purpose='import')
        snapshot = {'fields': {'旧附件字段': str(main.pk), '重复': main.pk.hex,
                             '越权': str(foreign.pk), '头像': str(avatar.pk), '导入源': str(source.pk),
                             '缺失': str(uuid.uuid4()), '普通文本': '保留原文'},
                    'details': {'旧明细字段': [{'附件': str(detail.pk)}, {'重复': str(main.pk)}]}}
        requests = apps.get_model('approvals', 'ApprovalRequest').objects
        application = requests.create(title='旧业务审批', applicant_id=user.pk, assignee_id=user.pk,
            business_module='no_longer_installed', business_record_id=uuid.uuid4(), business_snapshot=snapshot)
        plain = requests.create(title='普通审批', applicant_id=user.pk, assignee_id=user.pk, business_snapshot=snapshot)
        invalid = requests.create(title='坏格式', applicant_id=user.pk, assignee_id=user.pk,
            business_module='old', business_record_id=uuid.uuid4(), business_snapshot=['legacy'])
        MigrationExecutor(connection).migrate(latest)
        from apps.approvals.models import ApprovalFileReference, ApprovalRequest
        from apps.files.models import FileModel
        from apps.files.references import is_referenced
        assert set(ApprovalFileReference.objects.filter(request_id=application.pk).values_list('file_id', flat=True)) == {main.pk, detail.pk}
        assert not ApprovalFileReference.objects.filter(request_id__in=[plain.pk, invalid.pk]).exists()
        assert ApprovalRequest.objects.get(pk=application.pk).business_snapshot == snapshot
        restored = FileModel.objects.get(pk=main.pk)
        assert restored.file.name == 'legacy/unchanged.txt' and restored.lifecycle_version == 7
        assert is_referenced(restored) and FileModel.objects.get(pk=detail.pk).is_deleted
        assert not ApprovalFileReference.objects.exclude(tenant_id=None).exists()
    finally:
        MigrationExecutor(connection).migrate(latest)
