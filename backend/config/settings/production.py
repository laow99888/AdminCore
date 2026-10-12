"""
生产环境配置
"""

from .base import *

DEBUG = False

# 检查必需的环境变量（数据库通过 DB_* 分立变量配置，见 base.py）
import os

required_env_vars = ['DJANGO_SECRET_KEY']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]

if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# 静态文件
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# 允许的主机
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost').split(',')
