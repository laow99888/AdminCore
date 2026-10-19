"""隔离运行生产部署检查；不读取凭据、不连接业务数据库。"""
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
for key in list(os.environ):
    if key.startswith(('DJANGO_', 'ADMINCORE_', 'DB_', 'CELERY_', 'AUTH_', 'EMAIL_')) or key in ('DATABASE_URL', 'REDIS_URL'):
        os.environ.pop(key)
os.environ.update(PYTHON_DOTENV_DISABLED='1', DJANGO_ENV='production', DJANGO_SETTINGS_MODULE='config.settings.production',
                  DJANGO_DEBUG='False',
                  DJANGO_SECRET_KEY=secrets.token_urlsafe(64), DB_PASSWORD=secrets.token_urlsafe(40),
                  DJANGO_ALLOWED_HOSTS='localhost', USE_TLS='True', SECURE_HSTS_SECONDS='31536000')
sys.path.insert(0, str(ROOT / 'backend'))
import django
from django.core.checks import run_checks

django.setup()
issues = run_checks(include_deployment_checks=True)
allowed = {'security.W005', 'security.W021'}
failures = [issue for issue in issues if issue.id not in allowed]
for issue in issues:
    print(issue.id + ': ' + issue.msg)
if failures:
    raise SystemExit(1)
print('生产配置部署检查通过；子域 HSTS/preload 由部署方明确决定。')
