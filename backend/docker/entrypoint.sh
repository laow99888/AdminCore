#!/bin/sh
# AdminCore 后端启动入口：迁移 -> 初始化基础数据及维护计划 -> 启动服务
set -e

# 模块依赖或生产预设非法时立即失败，不伪装成“等待数据库”。
python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); from django.conf import settings; print('>>> 模块预设:', settings.ADMINCORE_PRESET)"

echo ">>> 等待数据库就绪..."
until python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.db import connection
connection.ensure_connection()
" 2>/dev/null; do
  sleep 2
done

echo ">>> 执行数据库迁移..."
python manage.py migrate --noinput

if [ "${1:-}" = "gunicorn" ]; then
  echo ">>> 初始化基础数据（生产不创建演示账户）..."
  python manage.py bootstrap_admincore
fi

echo ">>> 启动: $@"
exec "$@"
