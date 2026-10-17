"""安全的主库/只读副本路由。

只有 HTTP 安全方法在显式启用副本时读副本；写请求、事务、后台任务和
写后短暂一致性窗口全部读主库。副本连接失败时，安全读请求只重试一次主库。
"""

from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings
from django.core import signing
from django.db import connections


REPLICA_ALIAS = "replica"
PRIMARY_ALIAS = "default"
STICKY_COOKIE = "admincore_primary_until"
STICKY_SECONDS_SETTING = "ADMINCORE_DB_PRIMARY_STICKY_SECONDS"

_state = ContextVar("admincore_db_routing", default=None)


def _new_state(method="", allow_replica=False):
    return {
        "method": method.upper(),
        "allow_replica": bool(allow_replica),
        "force_primary": False,
        "write_seen": False,
        "replica_used": False,
    }


def enabled():
    return bool(getattr(settings, "ADMINCORE_DB_READ_REPLICA_ENABLED", False)
                and REPLICA_ALIAS in connections.databases)


def start_request(method, sticky=False):
    safe = method.upper() in {"GET", "HEAD", "OPTIONS"}
    state = _new_state(method, enabled() and safe)
    state["force_primary"] = bool(sticky)
    return _state.set(state)


def finish_request(token):
    _state.reset(token)


def current_state():
    return _state.get()


def mark_write():
    state = _state.get()
    if state is not None:
        state["write_seen"] = True
        state["force_primary"] = True


def should_fallback():
    state = _state.get()
    return bool(state and state["replica_used"] and state["allow_replica"]
                and not state["write_seen"] and not state["force_primary"])


def force_primary():
    state = _state.get()
    if state is not None:
        state["force_primary"] = True


def sticky_cookie_value():
    seconds = int(getattr(settings, STICKY_SECONDS_SETTING, 30))
    return signing.TimestampSigner(salt=STICKY_COOKIE).sign("1"), seconds


def has_valid_sticky_cookie(value):
    if not value:
        return False
    try:
        signing.TimestampSigner(salt=STICKY_COOKIE).unsign(
            value, max_age=int(getattr(settings, STICKY_SECONDS_SETTING, 30)))
    except (signing.BadSignature, signing.SignatureExpired, ValueError):
        return False
    return True


@contextmanager
def read_replica():
    """为明确的只读服务代码提供副本上下文，事务内仍强制主库。"""
    token = _state.set(_new_state("GET", enabled()))
    try:
        yield
    finally:
        _state.reset(token)


class PrimaryReplicaRouter:
    """Django database router with transaction and write-after-read guards."""

    def db_for_read(self, model, **hints):
        # 身份、会话、权限、租户与安全配置必须看到主库最新撤销状态。
        if getattr(getattr(model, '_meta', None), 'app_label', None) in {'auth_app', 'permissions', 'core', 'sessions', 'token_blacklist'}:
            return PRIMARY_ALIAS
        state = _state.get()
        if not enabled() or state is None or not state["allow_replica"]:
            return PRIMARY_ALIAS
        if state["force_primary"] or connections[PRIMARY_ALIAS].in_atomic_block:
            return PRIMARY_ALIAS
        state["replica_used"] = True
        return REPLICA_ALIAS

    def db_for_write(self, model, **hints):
        mark_write()
        return PRIMARY_ALIAS

    def allow_relation(self, obj1, obj2, **hints):
        db1, db2 = obj1._state.db, obj2._state.db
        if db1 and db2:
            return db1 == db2
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return db == PRIMARY_ALIAS
