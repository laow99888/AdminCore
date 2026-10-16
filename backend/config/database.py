"""数据库连接配置。

读写分离默认关闭。启用时必须显式提供独立的只读连接参数，避免把同一
个数据库误配置成两个别名后产生虚假的高可用假象。
"""

import os

from django.core.exceptions import ImproperlyConfigured


_TRUE = {"1", "true", "yes", "on"}


def is_enabled(value: str) -> bool:
    return value.strip().lower() in _TRUE


def _required(environ, name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"启用读写分离后必须配置 {name}，只读库不能隐式复用主库连接"
        )
    return value


def load_databases(environ=None):
    """返回 Django DATABASES，并校验显式的只读副本配置。"""
    if environ is None:
        environ = os.environ
    default = {
        "ENGINE": environ.get("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": environ.get("DB_NAME", "admincore"),
        "USER": environ.get("DB_USER", "postgres"),
        "PASSWORD": environ.get("DB_PASSWORD", "postgres"),
        "HOST": environ.get("DB_HOST", "localhost"),
        "PORT": environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": 600,
        "OPTIONS": {"connect_timeout": 10},
    }
    if not is_enabled(environ.get("ADMINCORE_DB_READ_REPLICA_ENABLED", "False")):
        return {"default": default}

    replica = {
        "ENGINE": _required(environ, "DB_REPLICA_ENGINE"),
        "NAME": _required(environ, "DB_REPLICA_NAME"),
        "USER": _required(environ, "DB_REPLICA_USER"),
        "PASSWORD": _required(environ, "DB_REPLICA_PASSWORD"),
        "HOST": _required(environ, "DB_REPLICA_HOST"),
        "PORT": _required(environ, "DB_REPLICA_PORT"),
        "CONN_MAX_AGE": 600,
        "OPTIONS": {"connect_timeout": 5},
    }
    identity = lambda config: tuple(config.get(key) for key in
                                    ("ENGINE", "NAME", "USER", "HOST", "PORT"))
    if identity(default) == identity(replica):
        raise ImproperlyConfigured("DB_REPLICA_* 必须指向独立的只读数据库")
    return {"default": default, "replica": replica}
