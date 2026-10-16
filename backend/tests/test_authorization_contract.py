"""API 路由授权契约回归。

这不是对象级越权测试；它负责发现新增路由意外使用 AllowAny，或把公开入口
扩展到未登记的路径。对象范围和撤权语义由各模块的专项测试覆盖。
"""

import pytest
import re
from django.urls import get_resolver
from django.urls.resolvers import URLPattern
from rest_framework.permissions import AllowAny

from apps.core.authorization_contract import classify_route, is_public_route, permission_names


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
