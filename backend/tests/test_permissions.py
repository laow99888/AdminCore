"""
权限模块测试：菜单接口、角色 CRUD 与权限分配
"""

import pytest
from apps.permissions.models import Menu, Permission, Role

pytestmark = pytest.mark.django_db


def unwrap_list(body):
    """兼容统一响应包里分页({data:{items}})与非分页({data:[...]})两种列表形态"""
    data = body.get('data', body) if isinstance(body, dict) else body
    if isinstance(data, dict):
        return data.get('items', data.get('results', []))
    return data


@pytest.fixture
def menu_tree():
    """构造 根菜单 -> 子菜单 两级结构"""
    root = Menu.objects.create(name='系统管理', path='/system', order=1)
    Menu.objects.create(name='用户管理', path='/system/users', order=2, parent=root)
    Menu.objects.create(name='角色管理', path='/system/roles', order=1, parent=root)
    return root


class TestMenuApi:
    def test_menu_list_returns_tree(self, admin_client, menu_tree):
        """回归：Menu 默认排序含自引用外键曾导致 Infinite loop caused by ordering (500)"""
        res = admin_client.get('/api/v1/permissions/menus/')
        assert res.status_code == 200
        roots = unwrap_list(res.json())
        assert len(roots) == 1
        root = roots[0]
        assert root['name'] == '系统管理'
        assert [c['name'] for c in root['children']] == ['角色管理', '用户管理']  # 按 order 排序

    def test_menu_list_requires_auth(self, client):
        res = client.get('/api/v1/permissions/menus/')
        assert res.status_code == 401

    def test_my_menu_contains_root(self, admin_client, menu_tree):
        res = admin_client.get('/api/v1/permissions/menus/my_menu/')
        assert res.status_code == 200
        assert '系统管理' in res.content.decode()


class TestRoleApi:
    def test_role_create_with_permissions(self, admin_client):
        perm = Permission.objects.create(
            name='查看用户', code='user:view', resource='user', action='view'
        )
        res = admin_client.post(
            '/api/v1/permissions/roles/',
            {'name': '运营', 'description': '', 'permission_ids': [str(perm.id)]},
            format='json',
        )
        assert res.status_code == 201
        data = res.json()['data']
        assert [p['code'] for p in data['permissions']] == ['user:view']
        role = Role.objects.get(id=data['id'])
        # role.permissions 是 RolePermission 反向管理器，权限明细需经中间表查
        assert list(
            Permission.objects.filter(rolepermission__role=role).values_list('id', flat=True)
        ) == [perm.id]

    def test_role_create_without_permission_ids(self, admin_client):
        """回归：permission_ids 曾因缺 required=False 导致创建必 400"""
        res = admin_client.post(
            '/api/v1/permissions/roles/',
            {'name': '访客'},
            format='json',
        )
        assert res.status_code == 201
        assert res.json()['data']['permissions'] == []

    def test_role_update_rebuilds_permissions(self, admin_client):
        perms = Permission.objects.bulk_create([
            Permission(name='查看用户', code='user:view', resource='user', action='view'),
            Permission(name='编辑用户', code='user:edit', resource='user', action='edit'),
        ])
        res = admin_client.post(
            '/api/v1/permissions/roles/',
            {'name': '运营', 'permission_ids': [str(perms[0].id)]},
            format='json',
        )
        role_id = res.json()['data']['id']
        res = admin_client.patch(
            f'/api/v1/permissions/roles/{role_id}/',
            {'version': 1, 'permission_ids': [str(perms[1].id)]},
            format='json',
        )
        assert res.status_code == 200
        assert [p['code'] for p in res.json()['data']['permissions']] == ['user:edit']

    def test_permission_list(self, admin_client):
        Permission.objects.create(name='查看用户', code='user:view', resource='user', action='view')
        res = admin_client.get('/api/v1/permissions/permissions/')
        assert res.status_code == 200
        assert any(p['code'] == 'user:view' for p in unwrap_list(res.json()))
