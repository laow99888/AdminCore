"""API 授权契约的集中定义。

视图仍以 DRF 的 permission_classes 为最终执行点；本模块只提供路由审计
所需的公开入口白名单和语义分类，避免新路由意外变成匿名可用。
"""

from __future__ import annotations

from collections.abc import Iterable


# 这些入口在没有 Bearer 会话时也必须可用：登录、恢复、验证码、公开品牌、
# 健康探针及 SSO 浏览器跳转。新增匿名入口必须同时更新此集合和回归测试。
PUBLIC_ROUTE_PREFIXES = (
    "/api/versions/",
    "/api/v1/health/",
    "/api/v1/brand/",
    "/api/v1/auth/login",
    "/api/v1/auth/login-captcha/",
    "/api/v1/auth/recovery/",
    "/api/v1/auth/refresh/",
    "/api/v1/auth/register/",
    "/api/v1/sso/config/",
    "/api/v1/sso/start/",
    "/api/v1/sso/callback/",
    "/api/v1/sso/status/",
    "/api/v1/sso/complete/",
    "/api/v1/sso/cancel/",
)


def is_public_route(path: str) -> bool:
    """返回是否属于明确登记的匿名入口。"""

    return any(path.startswith(prefix) for prefix in PUBLIC_ROUTE_PREFIXES)


def permission_names(permissions: Iterable[type] | None) -> set[str]:
    """把 DRF 权限类转换成稳定的审计名称。"""

    return {getattr(permission, "__name__", str(permission)) for permission in (permissions or ())}


def classify_route(path: str, permissions: Iterable[type] | None) -> str:
    """按最严格的声明给路由归类，供文档和检查使用。"""

    names = permission_names(permissions)
    if is_public_route(path) or "AllowAny" in names:
        return "public"
    if "IsAdmin" in names:
        return "admin"
    if "HasPermission" in names:
        return "permission"
    return "self"

\n