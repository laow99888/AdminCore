"""
Django 配置初始化
根据环境变量选择配置
"""

import os
from .base import *

# 根据 DJANGO_ENV 选择配置
ENV = os.getenv('DJANGO_ENV', 'development')

if ENV == 'production':
    from .production import *
elif ENV == 'testing':
    from .testing import *
else:
    from .development import *
