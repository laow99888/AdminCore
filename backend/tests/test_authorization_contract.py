"""API 路由授权契约回归。

这不是对象级越权测试；它负责发现新增路由意外使用 AllowAny，或把公开入口
扩展到未登记的路径。对象范围和撤权语义由各模块的专项测试覆盖。
"""

import pytest
import re
from django.urls import get_resolver
from django.urls.resolvers import URLPattern
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

from apps.core.authorization_contract import classify_route, is_public_route, permission_names


@pytest.mark.parametrize('path', [
    '/api/v1/auth/login-history/', '/api/v1/auth/login/admin/',
    '/api/v1/auth/recovery/admin/', '/api/v1/health/private/',
    '/api/v1/brand/admin/', '/api/v1/sso/status/admin/',
    '/api/versions/private/', '/api/v1/auth/register/admin/',
])
def test_new_routes_do_not_inherit_anonymous_prefixes(path):
    assert not is_public_route(path)


@pytest.mark.django_db
@pytest.mark.parametrize('method,path', [
    ('get', '/api/v1/auth/me/'), ('get', '/api/v1/auth/profile/'),
    ('patch', '/api/v1/auth/profile/'), ('post', '/api/v1/auth/logout/'),
    ('post', '/api/v1/auth/change_password/'), ('get', '/api/v1/auth/sessions/'),
    ('delete', '/api/v1/auth/sessions/00000000-0000-4000-8000-000000000001/'),
    ('get', '/api/v1/auth/online-users/'), ('get', '/api/v1/modules/'),
    ('get', '/api/v1/dashboard/stats/'), ('get', '/api/v1/users/'),
    ('post', '/api/v1/users/'), ('patch', '/api/v1/users/00000000-0000-4000-8000-000000000001/'),
    ('delete', '/api/v1/users/00000000-0000-4000-8000-000000000001/'),
    ('get', '/api/v1/permissions/roles/'), ('post', '/api/v1/permissions/roles/'),
    ('get', '/api/v1/permissions/permissions/'), ('get', '/api/v1/permissions/menus/'),
    ('get', '/api/v1/logs/login/'), ('get', '/api/v1/logs/operation/'),
    ('get', '/api/v1/logs/exception/'),
])
def test_private_core_http_routes_reject_anonymous_requests(method, path):
    response = getattr(APIClient(), method)(path, **({} if method == 'get' else {'data': {}, 'format': 'json'}))
    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize('path', [
    '/api/v1/users/', '/api/v1/permissions/roles/',
    '/api/v1/permissions/menus/', '/api/v1/logs/login/', '/api/v1/logs/operation/',
    '/api/v1/logs/exception/', '/api/v1/auth/online-users/',
])
def test_member_without_business_permissions_cannot_read_management_routes(member_client, path):
    assert member_client.get(path).status_code == 403


@pytest.mark.django_db
def test_permission_definition_catalog_remains_authenticated_and_read_only(member_client):
    from apps.permissions.models import Permission
    definition = Permission.objects.create(code='fixture:read', name='只读定义', resource='fixture', action='read')
    response = member_client.get('/api/v1/permissions/permissions/' + str(definition.pk) + '/')
    assert response.status_code == 200 and response.data['data']['code'] == 'fixture:read'
    assert member_client.post('/api/v1/permissions/permissions/', {'code': 'fixture:write'}, format='json').status_code == 405
    for method in ('put', 'patch', 'delete'):
        response = getattr(member_client, method)('/api/v1/permissions/permissions/' + str(definition.pk) + '/',
                                                  {'name': '意外修改'}, format='json')
        assert response.status_code == 405
    definition.refresh_from_db()
    assert definition.name == '只读定义'
    assert not Permission.objects.filter(code='fixture:write').exists()


def _effective_permissions(item):
    callback = item.callback
    view_class = getattr(callback, "cls", None)
    initkwargs = getattr(callback, "initkwargs", {}) or {}
    if view_class is None:
        return None
    return initkwargs.get("permission_classes", getattr(view_class, "permission_classes", None))


@pytest.mark.django_db
def test_api_routes_have_explicit_anonymous_contract():
    """所有匿名能力必须在白名单登记，其他 API 继承认证保护。"""

    unknown_public = []
    resolver = get_resolver()

    def inspect(patterns, prefix=""):
        for item in patterns:
            if isinstance(item, URLPattern):
                raw = prefix + str(item.pattern)
                if not raw.startswith("api/") or "<drf_format_suffix" in raw or "(?P<format>" in raw:
                    continue
                path = "/" + re.sub(r"[\^$]", "", raw)
                permissions = _effective_permissions(item)
                names = permission_names(permissions)
                if permissions is None:
                    # 函数视图没有 cls；只有已登记的健康/版本探针允许此形态。
                    if not is_public_route(path):
                        unknown_public.append((path, "function-without-permission-class"))
                elif not permissions and not is_public_route(path):
                    unknown_public.append((path, "empty-permission-classes"))
                elif AllowAny.__name__ in names and not is_public_route(path):
                    unknown_public.append((path, sorted(names)))
                assert classify_route(path, permissions) in {"public", "self", "permission", "admin"}
            else:
                inspect(item.url_patterns, prefix + str(item.pattern))

    inspect(resolver.url_patterns)
    assert unknown_public == []
