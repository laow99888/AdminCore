"""内置模块唯一静态声明；不导入模型或访问数据库。"""
from apps.core.contracts import Module, MenuDeclaration

MODULE = Module('approvals', '单级审批', 'approvals', 'apps.approvals.urls', ('/approvals',), ('notifications',),
    permissions=(
        ('approval', 'read', '查看审批', 'approval:read'),
        ('approval', 'decide', '审批处理', 'approval:decide'),
    ),
    audit_fields=(
        ('approval', ('id', 'status', 'request_type', 'applicant_id', 'assignee_id', 'decided_by_id', 'decided_at')),
    ),
    menus=(
        MenuDeclaration('审批工作流', '/approvals', 'clipboard-check', None, 6),
    ))
