#!/bin/sh
# AdminCore 后端启动入口：迁移 -> 初始化基础数据及维护计划 -> 启动服务
set -e

# 模块依赖或生产预设非法时立即失败，不伪装成“等待数据库”。
python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); from django.conf import settings; print('>>> 模块预设:', settings.ADMINCORE_PRESET)"

echo ">>> 等待数据库并协调初始化（最长 180 秒）..."
if [ "${1:-}" = "gunicorn" ]; then
  python manage.py initialize_runtime --bootstrap
else
  python manage.py initialize_runtime
fi

echo ">>> 启动: $@"
exec "$@"
