"""从旧审批表实际升级，不重分配待办、不追补旧节点时限。"""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_old_requests_keep_flow_version_and_assignee():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old = [('approvals', '0006_approvalstep_assignment_context')]
    try:
        executor.migrate(old)
        # 只回退目标 app；其余应用仍处于实际已应用版本，历史模型必须与整库一致。
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
        user = apps.get_model('auth_app', 'User').objects.create(username='legacy-workflow')
        flow = apps.get_model('approvals', 'ApprovalFlow').objects.create(name='旧流程', code='legacy', version=7,
            status='published', definition={'nodes': []}, created_by_id=user.pk)
        request = apps.get_model('approvals', 'ApprovalRequest').objects.create(applicant_id=user.pk, assignee_id=user.pk,
            title='旧待办', content='内容', flow_id=flow.pk, flow_version=7, workflow_version=3, current_node='review')
        step = apps.get_model('approvals', 'ApprovalStep').objects.create(request_id=request.pk, assignee_id=user.pk,
            node_key='review', sequence=2, assignment_context={'source': 'legacy'})
        MigrationExecutor(connection).migrate(latest)
        from apps.approvals.models import ApprovalFlow, ApprovalRequest, ApprovalStep
        restored = ApprovalRequest.objects.get(pk=request.pk)
        assert restored.flow_version == 7 and restored.workflow_version == 3 and restored.return_count == 0
        assert restored.flow_id == flow.pk and restored.assignee_id == user.pk
        assert ApprovalFlow.objects.get(pk=flow.pk).revision == 1
        restored_step = ApprovalStep.objects.get(pk=step.pk)
        assert restored_step.status == 'pending' and restored_step.due_at is None and restored_step.escalate_at is None
        assert restored_step.assignment_context == {'source': 'legacy'}
    finally:
        MigrationExecutor(connection).migrate(latest)
