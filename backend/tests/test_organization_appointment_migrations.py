"""旧库升级不推断主管、不重写归属，也不重分配历史待办。"""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_upgrade_preserves_membership_and_pending_step():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old = [('core', '0012_alter_datascopegrant_resource'), ('approvals', '0005_approvalrequest_business_binding')]
    try:
        executor.migrate(old)
        # 只回退目标 app；其余应用仍处于实际已应用版本，历史模型必须与整库一致。
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
        user = apps.get_model('auth_app', 'User').objects.create(username='legacy-org')
        department = apps.get_model('core', 'Department').objects.create(name='旧部门')
        membership = apps.get_model('core', 'OrganizationMembership').objects.create(user_id=user.pk, department_id=department.pk)
        request = apps.get_model('approvals', 'ApprovalRequest').objects.create(applicant_id=user.pk, assignee_id=user.pk, title='旧待办', content='内容')
        step = apps.get_model('approvals', 'ApprovalStep').objects.create(request_id=request.pk, assignee_id=user.pk, node_key='review', kind='user', mode='all', sequence=0)
        MigrationExecutor(connection).migrate(latest)
        from apps.core.models import Department, OrganizationAppointment, OrganizationMembership
        from apps.approvals.models import ApprovalStep
        assert Department.objects.get(pk=department.pk).leader_id is None
        assert OrganizationMembership.objects.get(pk=membership.pk).department_id == department.pk
        assert not OrganizationAppointment.objects.filter(user_id=user.pk).exists()
        restored = ApprovalStep.objects.get(pk=step.pk)
        assert restored.assignee_id == user.pk and restored.assignment_context == {} and restored.status == 'pending'
    finally:
        MigrationExecutor(connection).migrate(latest)
