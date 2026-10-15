"""仅供本机独立演示项目；生产部署不得选择本配置。"""
from .base import *
from django.core.exceptions import ImproperlyConfigured

if os.getenv('DJANGO_ENV') != 'demo' or ADMINCORE_PRESET != 'demo':
    raise ImproperlyConfigured('演示配置要求独立的 demo 环境和预设')
if not os.getenv('ADMINCORE_DEMO_INSTANCE'):
    raise ImproperlyConfigured('演示项目缺少实例身份，请使用 scripts/demo_project.py 创建')

DEBUG = False
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'backend']
ALLOW_PUBLIC_REGISTRATION = False
