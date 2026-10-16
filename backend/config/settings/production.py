"""
生产环境配置
"""

from .base import *

DEBUG = False

# 检查必需的环境变量（数据库通过 DB_* 分立变量配置，见 base.py）
import os
from django.core.exceptions import ImproperlyConfigured

required_env_vars = ['DJANGO_SECRET_KEY', 'DB_PASSWORD']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]

if missing_vars:
    raise ImproperlyConfigured(f"Missing required environment variables: {', '.join(missing_vars)}")

if len(os.environ['DB_PASSWORD']) < 16 or os.environ['DB_PASSWORD'].strip().casefold() in {
        'postgres', 'password', 'changeme', 'your-db-password'}:
    raise ImproperlyConfigured('生产环境必须显式配置至少 16 字符的 DB_PASSWORD')

if (len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5
        or SECRET_KEY.startswith('django-insecure-')
        or SECRET_KEY == 'your-secret-key-change-in-production'):
    raise ImproperlyConfigured('生产环境必须配置至少 50 字符的随机 DJANGO_SECRET_KEY')

# 静态文件
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# 允许的主机
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost').split(',')
