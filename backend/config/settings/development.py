"""
开发环境配置
"""

from .base import *

DEBUG = True
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]').split(',')

if SECRET_KEY.startswith('django-insecure-'):
    import warnings
    warnings.warn('Development uses an insecure default key; configure DJANGO_SECRET_KEY and never expose DEBUG publicly.', RuntimeWarning)

# 开发工具
if DEBUG:
    INSTALLED_APPS += [
        'django_extensions',
    ]
