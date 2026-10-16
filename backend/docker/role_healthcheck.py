"""worker/beat 的轻量探针：检查进程角色、数据库和 Redis 连接。"""
import os
import sys

import django


role = sys.argv[1] if len(sys.argv) > 1 else ""
command_line = open("/proc/1/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="ignore")
if role not in command_line:
    raise SystemExit(f"进程角色不匹配: {command_line}")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.db import connection  # noqa: E402

connection.ensure_connection()
from django.conf import settings  # noqa: E402

if not settings.CELERY_BROKER_URL.startswith("redis"):
    raise SystemExit("worker/beat healthcheck 需要 Redis broker")
import redis  # noqa: E402

redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2, socket_timeout=2).ping()
