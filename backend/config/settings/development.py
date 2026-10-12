"""
开发环境配置
"""

from .base import *

DEBUG = True
ALLOWED_HOSTS = ['*']

# 开发工具
if DEBUG:
    INSTALLED_APPS += [
        'django_extensions',
    ]
