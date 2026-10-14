"""
AdminCore Django 基础配置
"""

import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
from config.storage import storage_settings

# 加载环境变量
load_dotenv()

from apps.core.modules import resolve_modules

ADMINCORE_PRESET = os.getenv('ADMINCORE_PRESET', 'standard')
ADMINCORE_MODULES = resolve_modules(ADMINCORE_PRESET, os.getenv('ADMINCORE_MODULES'),
                                  production=os.getenv('DJANGO_ENV') == 'production')

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BASE_DIR.parent

# 安全配置
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-dev-key-change-in-production')
DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() == 'true'
ALLOW_PUBLIC_REGISTRATION = os.getenv('ALLOW_PUBLIC_REGISTRATION', 'False').lower() == 'true'
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0').split(',')

# 应用配置
INSTALLED_APPS = [
    # Django 内置
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # 第三方
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'django_celery_beat',

    # 项目应用
    'apps.core',
    'apps.auth_app',
    'apps.users',
    'apps.permissions',
    'apps.files',
    'apps.tasks',
    'apps.logs',
    'apps.notifications',
    'apps.data_io',
    'apps.approvals',
]

# 中间件
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # 静态文件
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # CORS
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.middleware.PasswordChangeSessionMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # 自定义中间件
    'apps.core.middleware.RequestTrackingMiddleware',
    'apps.core.middleware.ErrorHandlingMiddleware',
    'apps.core.module_middleware.ModuleGateMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ===== 数据库配置 =====
DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.postgresql'),
        'NAME': os.getenv('DB_NAME', 'admincore'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'postgres'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'CONN_MAX_AGE': 600,
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# ===== 用户模型 =====
# 使用 auth_app 中定义的自定义用户模型（UUID 主键 + 头像/电话/登录统计字段）
AUTH_USER_MODEL = 'auth_app.User'

# ===== 密码验证 =====
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ===== 国际化 =====
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

# ===== 静态文件 =====
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
ADMINCORE_STORAGE_BACKEND = os.getenv('ADMINCORE_STORAGE_BACKEND', 'local')
STORAGES = storage_settings(os.environ)

# ===== 文件上传配置 =====
# 单文件大小上限（默认 50MB）
FILE_UPLOAD_MAX_SIZE = int(os.getenv('FILE_UPLOAD_MAX_SIZE', str(50 * 1024 * 1024)))
# 预览比下载更严格：限制输入、解码像素和 PDF 页数。
FILE_PREVIEW_MAX_SIZE = 10 * 1024 * 1024
FILE_PREVIEW_MAX_PIXELS = 16_000_000
FILE_PREVIEW_MAX_PDF_PAGES = 100
# 允许的文件扩展名白名单（不含点，统一小写比较）
FILE_UPLOAD_ALLOWED_EXTENSIONS = [
    # 图片
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'ico', 'bmp',
    # 文档
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'md', 'csv', 'json',
    # 压缩包
    'zip', 'gz', 'tar', 'tgz', '7z', 'rar',
]
# 软删除文件保留天数，超期后由清理任务物理删除
FILE_SOFT_DELETE_RETENTION_DAYS = int(os.getenv('FILE_SOFT_DELETE_RETENTION_DAYS', '30'))
# 已读通知保留天数，超期后由清理任务删除
NOTIFICATION_RETENTION_DAYS = int(os.getenv('NOTIFICATION_RETENTION_DAYS', '90'))

# ===== REST Framework 配置 =====
REST_FRAMEWORK = {
    # 认证
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.auth_app.authentication.SessionJWTAuthentication',
    ),
    # 权限
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    # 分页
    'DEFAULT_PAGINATION_CLASS': 'apps.core.pagination.StandardPagination',
    'PAGE_SIZE': 10,
    # 过滤
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    # 限流
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
    # 默认直连只信任 REMOTE_ADDR；Compose 通过覆盖转发头的 Nginx 使用单层代理。
    'NUM_PROXIES': int(os.getenv('DRF_NUM_PROXIES', '0')),
    # 其他
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'AdminCore API',
    'VERSION': '1.0.0',
    'COMPONENT_SPLIT_REQUEST': True,
    'SERVE_PERMISSIONS': ['apps.permissions.permissions.IsAdmin'],
    'SWAGGER_UI_SETTINGS': {'persistAuthorization': False},
}

# ===== JWT 配置 =====
SIMPLE_JWT = {
    'CHECK_REVOKE_TOKEN': True,
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=5),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}

# ===== CORS 配置 =====
CORS_ALLOWED_ORIGINS = os.getenv(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173'
).split(',')

CORS_ALLOW_CREDENTIALS = True
from corsheaders.defaults import default_headers
CORS_ALLOW_HEADERS = (*default_headers, 'idempotency-key', 'x-request-id')
CORS_EXPOSE_HEADERS = ['X-Request-ID', 'Idempotency-Replayed']

# ===== Redis 配置 =====
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# ===== Celery 配置 =====
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
# 定时任务调度器（django-celery-beat，任务计划存数据库）
CELERY_BEAT_SCHEDULER = 'apps.core.module_scheduler.ModuleScheduler'

# ===== 缓存配置 =====
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 2,
            'SOCKET_TIMEOUT': 2,
        }
    }
}

# ===== 日志配置 =====
# 精简部署无需 Redis/worker；单进程限流使用本地缓存。
if not ADMINCORE_MODULES:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# RotatingFileHandler 不会自动创建目录，这里显式保证日志目录存在
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'django.log'),
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}

# ===== 默认主键类型 =====
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ===== 安全设置 =====
# TLS 相关开关：仅在前置 HTTPS 网关终结 TLS 时启用（USE_TLS=True），
# 否则 http 部署会被 SECURE_SSL_REDIRECT 重定向到不可达的 https
USE_TLS = os.getenv('USE_TLS', 'False').lower() == 'true'

if not DEBUG:
    SECURE_SSL_REDIRECT = USE_TLS
    SESSION_COOKIE_SECURE = USE_TLS
    CSRF_COOKIE_SECURE = USE_TLS
    if USE_TLS:
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '0')) if USE_TLS else 0
