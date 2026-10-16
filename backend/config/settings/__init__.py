"""
Django 配置初始化
根据环境变量选择配置
"""

import os
from dotenv import load_dotenv

load_dotenv()

# 显式 settings 子模块可供 pytest/终端使用；通用入口必须声明运行环境。
from django.core.exceptions import ImproperlyConfigured

_profile = os.getenv('DJANGO_SETTINGS_MODULE', '').removeprefix('config.settings.')
ENV = os.getenv('DJANGO_ENV', _profile if _profile in ('development', 'testing', 'production', 'demo') else '')
if ENV not in ('development', 'testing', 'production', 'demo'):
    raise ImproperlyConfigured('必须显式设置 DJANGO_ENV 为 development、testing、production 或 demo')
if _profile in ('development', 'testing', 'production', 'demo') and _profile != ENV:
    raise ImproperlyConfigured('DJANGO_ENV 与显式 settings 模块不一致')
os.environ.setdefault('DJANGO_ENV', ENV)

from .base import *

if ENV == 'production':
    from .production import *
elif ENV == 'testing':
    from .testing import *
elif ENV == 'demo':
    from .demo import *
else:
    from .development import *
