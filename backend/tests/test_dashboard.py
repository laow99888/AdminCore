"""
仪表盘统计与权限测试
"""


class TestDashboard:
    def test_stats_totals_and_trend(self, admin_client, member_client):
        # 制造一次成功与一次失败登录
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_user('extra', 'extra@example.com', 'Extra#12345')

        res = admin_client.get('/api/v1/dashboard/stats/')
        assert res.status_code == 200
        data = res.json()['data']

        totals = data['totals']
        assert totals['users'] >= 2
        assert totals['today_logins'] >= 2  # admin + member 登录

        trend = data['login_trend']
        assert len(trend) == 7
        assert trend[-1]['success'] >= 2
        assert isinstance(data['task_status'], dict)

    def test_stats_requires_auth(self, client):
        assert client.get('/api/v1/dashboard/stats/').status_code == 401


class TestAdminPermissionBoundary:
    def test_task_center_forbidden_for_member(self, member_client):
        assert member_client.get('/api/v1/tasks/').status_code == 403

    def test_roles_crud_for_admin(self, admin_client):
        from apps.permissions.models import Permission
        perm = Permission.objects.create(name='查看用户', code='user:read', resource='user', action='read')

        res = admin_client.post('/api/v1/permissions/roles/', {
            'name': '编辑', 'description': '内容编辑', 'permission_ids': [str(perm.id)],
        }, format='json')
        assert res.status_code == 201
        data = res.json()['data']
        role_id = data['id']
        assert len(data['permissions']) == 1  # 权限分配已生效

        res = admin_client.patch(f'/api/v1/permissions/roles/{role_id}/', {'description': '改'}, format='json')
        assert res.status_code == 200
        assert admin_client.delete(f'/api/v1/permissions/roles/{role_id}/').status_code == 200

    def test_role_create_without_permissions(self, admin_client):
        """不传 permission_ids 也应能创建角色"""
        res = admin_client.post('/api/v1/permissions/roles/', {'name': '访客'}, format='json')
        assert res.status_code == 201

    def test_roles_forbidden_for_member(self, member_client):
        assert member_client.get('/api/v1/permissions/roles/').status_code == 403
