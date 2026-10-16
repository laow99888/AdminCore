"""
AdminCore Django 基础配置
"""

import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
from config.storage import storage_settings
from config.antivirus import load_antivirus
from config.database import is_enabled, load_databases

# 加载环境变量
load_dotenv()
ADMINCORE_ANTIVIRUS = load_antivirus(os.environ)

from apps.core.modules import resolve_modules

ADMINCORE_PRESET = os.getenv('ADMINCORE_PRESET', 'standard')
ADMINCORE_MODULES = resolve_modules(ADMINCORE_PRESET, os.getenv('ADMINCORE_MODULES'),
                                  production=os.getenv('DJANGO_ENV') == 'production')
from config.build_profile import load_profile, validate_profile
ADMINCORE_BUILD_PROFILE = load_profile()
validate_profile(ADMINCORE_BUILD_PROFILE, ADMINCORE_MODULES,
                 os.getenv('ADMINCORE_STORAGE_BACKEND', 'local'),
                 os.getenv('ADMINCORE_IMAGE_PROCESSING_ENABLED', 'False').lower() == 'true')
from apps.core.api_lifecycle import load_configuration
ADMINCORE_API_LIFECYCLE = load_configuration(os.getenv('ADMINCORE_API_LIFECYCLE', '{}'))
ADMINCORE_MULTI_TENANT_ENABLED = os.getenv('ADMINCORE_MULTI_TENANT_ENABLED', 'False').lower() == 'true'

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BASE_DIR.parent

# 安全配置
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-dev-key-change-in-production')
DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() == 'true'
ALLOW_PUBLIC_REGISTRATION = os.getenv('ALLOW_PUBLIC_REGISTRATION', 'False').lower() == 'true'
# key 存在即加密手机号写入；ENABLED 用于要求部署必须配置有效密钥。
ADMINCORE_FIELD_ENCRYPTION_ENABLED = os.getenv('ADMINCORE_FIELD_ENCRYPTION_ENABLED', 'False').lower() == 'true'
ADMINCORE_FIELD_ENCRYPTION_KEY = os.getenv('ADMINCORE_FIELD_ENCRYPTION_KEY', '')
if ADMINCORE_FIELD_ENCRYPTION_ENABLED or ADMINCORE_FIELD_ENCRYPTION_KEY:
    from cryptography.fernet import Fernet
    from django.core.exceptions import ImproperlyConfigured
    try:
        Fernet(ADMINCORE_FIELD_ENCRYPTION_KEY.encode('ascii'))
    except (ValueError, UnicodeEncodeError):
        # 启动阶段错误需要能在 Windows 默认代码页下稳定传回诊断进程。
        raise ImproperlyConfigured('ADMINCORE_FIELD_ENCRYPTION_KEY must be a valid Fernet key') from None
# 独立于 JWT 签名密钥；缺失时不允许绑定，已有设备认证保持失败关闭。
AUTH_TOTP_ENCRYPTION_KEY = os.getenv('AUTH_TOTP_ENCRYPTION_KEY', '')
# 企业身份源显式配置；未启用 sso 模块时不发起身份源请求。
for _sso_setting in ('ISSUER', 'AUTHORIZATION_ENDPOINT', 'TOKEN_ENDPOINT', 'JWKS_URI', 'CLIENT_ID',
                     'CLIENT_SECRET', 'REDIRECT_URI', 'FRONTEND_ORIGIN', 'ENCRYPTION_KEY'):
    globals()['SSO_' + _sso_setting] = os.getenv('SSO_' + _sso_setting, '')
SSO_LABEL = os.getenv('SSO_LABEL', '企业身份登录')
SSO_SESSION_SECONDS = int(os.getenv('SSO_SESSION_SECONDS', '3600'))
if AUTH_TOTP_ENCRYPTION_KEY:
    from cryptography.fernet import Fernet
    try:
        Fernet(AUTH_TOTP_ENCRYPTION_KEY.encode('ascii'))
    except (ValueError, UnicodeEncodeError):
        raise ValueError('AUTH_TOTP_ENCRYPTION_KEY 必须为合法的 Fernet 密钥') from None
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0').split(',')
import ipaddress
from django.core.exceptions import ImproperlyConfigured
try:
    ADMINCORE_TRUSTED_PROXIES = tuple(ipaddress.ip_network(value.strip(), strict=False)
        for value in os.getenv('ADMINCORE_TRUSTED_PROXIES', '').split(',') if value.strip())
except ValueError:
    raise ImproperlyConfigured('ADMINCORE_TRUSTED_PROXIES 必须是逗号分隔的可信直接代理 IP/CIDR') from None

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
    'apps.example',
    'apps.api_credentials',
    'apps.sso',
    'apps.feature_flags',
    'apps.ip_policy',
    'apps.online_forms',
      'apps.reports',
]

# 中间件
MIDDLEWARE = [
    # 只装饰响应头，也覆盖安全重定向、CSRF 和 CORS 的提前响应。
    'apps.core.api_lifecycle.APILifecycleMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # 静态文件
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'apps.core.error_i18n.APIErrorI18nMiddleware',
    'apps.ip_policy.middleware.IPPolicyMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # CORS
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.tenancy_middleware.TenantContextMiddleware',
    'apps.core.middleware.PasswordChangeSessionMiddleware',
    'apps.core.db_routing_middleware.DatabaseRoutingMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # 自定义中间件
    'apps.core.middleware.RequestTrackingMiddleware',
    'apps.files.scan_middleware.ScanAuditMiddleware',
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
ADMINCORE_DB_READ_REPLICA_ENABLED = os.getenv(
    'ADMINCORE_DB_READ_REPLICA_ENABLED', 'False')
ADMINCORE_DB_READ_REPLICA_ENABLED = is_enabled(ADMINCORE_DB_READ_REPLICA_ENABLED)
ADMINCORE_DB_PRIMARY_STICKY_SECONDS = int(
    os.getenv('ADMINCORE_DB_PRIMARY_STICKY_SECONDS', '30'))
if not 1 <= ADMINCORE_DB_PRIMARY_STICKY_SECONDS <= 300:
    raise ImproperlyConfigured('ADMINCORE_DB_PRIMARY_STICKY_SECONDS 必须在 1–300 秒之间')
DATABASES = load_databases(os.environ)
DATABASE_ROUTERS = ['config.db_router.PrimaryReplicaRouter']

# 列表/安全导出按 SQL 限时，禁止 0（关闭）及无限放宽；不作用于迁移/任务。
from django.core.exceptions import ImproperlyConfigured
for _budget_name, _budget_default, _budget_max in [
    ('ADMINCORE_QUERY_STATEMENT_TIMEOUT_MS', 30_000, 300_000),
    ('ADMINCORE_QUERY_LOCK_TIMEOUT_MS', 2_000, 30_000),
]:
    try:
        _budget_value = int(os.getenv(_budget_name, str(_budget_default)))
    except ValueError:
        raise ImproperlyConfigured(f'{_budget_name} 必须为整数毫秒') from None
    if not 1 <= _budget_value <= _budget_max:
        raise ImproperlyConfigured(f'{_budget_name} 必须在 1–{_budget_max} 毫秒之间')
    globals()[_budget_name] = _budget_value

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
LANGUAGES = [('zh-hans', '简体中文'), ('en', 'English')]
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
# 按需启用的内存图片处理；不改写原件，不生成持久化派生文件。
ADMINCORE_IMAGE_PROCESSING_ENABLED = os.getenv('ADMINCORE_IMAGE_PROCESSING_ENABLED', 'False').lower() == 'true'
# Office 转换由宿主专属沙箱执行；Web 服务不挂载 Docker socket。
ADMINCORE_OFFICE_PREVIEW_ENABLED = os.getenv('ADMINCORE_OFFICE_PREVIEW_ENABLED', 'False').lower() == 'true'
ADMINCORE_OFFICE_IMAGE = os.getenv('ADMINCORE_OFFICE_IMAGE', '')
if ADMINCORE_OFFICE_PREVIEW_ENABLED:
    import re
    from django.core.exceptions import ImproperlyConfigured
    if (ADMINCORE_BUILD_PROFILE != 'full' or not {'files', 'tasks'} <= set(ADMINCORE_MODULES)
            or not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]{0,180}@sha256:[a-f0-9]{64}', ADMINCORE_OFFICE_IMAGE)):
        raise ImproperlyConfigured('Office 预览要求完整构建、文件与任务模块及固定摘要转换镜像')
# 允许的文件扩展名白名单（不含点，统一小写比较）
FILE_UPLOAD_ALLOWED_EXTENSIONS = [
    # 图片
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'ico', 'bmp',
    # 文档
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods', 'odp', 'txt', 'md', 'csv', 'json',
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
    'DEFAULT_SCHEMA_CLASS': 'apps.core.schema.QueryBudgetSchema',
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
}

from apps.core.version import BASE_VERSION

SPECTACULAR_SETTINGS = {
    'TITLE': 'AdminCore API',
    'VERSION': BASE_VERSION,
    'COMPONENT_SPLIT_REQUEST': True,
    'ENUM_NAME_OVERRIDES': {'OperationActionEnum': 'apps.logs.models.OperationLog.ACTION_CHOICES',
                          'TaskRecordStatusEnum': 'apps.tasks.models.TaskRecord.STATUS_CHOICES',
                          'WorkItemStatusEnum': [('open', '待处理'), ('done', '已完成')],
                          'TaskMetricStatusEnum': ['ok', 'degraded', 'disabled'],
                          'QueueMetricStatusEnum': ['ok', 'unavailable', 'disabled'],
                          'MessageChannelEnum': 'apps.notifications.models.MessageDelivery.CHANNELS',
                          'OnlineFormStatusEnum': 'apps.online_forms.models.OnlineForm.STATUS_CHOICES'},
    'SERVE_PERMISSIONS': ['apps.permissions.permissions.IsAdmin'],
    'SWAGGER_UI_SETTINGS': {'persistAuthorization': False},
    'POSTPROCESSING_HOOKS': ['drf_spectacular.hooks.postprocess_schema_enums',
                           'apps.core.api_lifecycle.schema_lifecycle'],
}

# ===== JWT 配置 =====
AUTH_SESSION_ABSOLUTE_SECONDS = int(os.getenv('AUTH_SESSION_ABSOLUTE_SECONDS', '86400'))
AUTH_SESSION_IDLE_SECONDS = int(os.getenv('AUTH_SESSION_IDLE_SECONDS', '1800'))
AUTH_SESSION_TOUCH_SECONDS = int(os.getenv('AUTH_SESSION_TOUCH_SECONDS', '60'))
AUTH_REAUTH_USER_FAILURE_LIMIT = 10
AUTH_REAUTH_SCOPE_FAILURE_LIMIT = 5
AUTH_LOGIN_CAPTCHA_ENABLED = os.getenv('AUTH_LOGIN_CAPTCHA_ENABLED', 'False').lower() == 'true'
AUTH_LOGIN_CAPTCHA_FAILURE_THRESHOLD = int(os.getenv('AUTH_LOGIN_CAPTCHA_FAILURE_THRESHOLD', '3'))
if not 1 <= AUTH_LOGIN_CAPTCHA_FAILURE_THRESHOLD <= 5:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('登录验证码失败门槛范围为 1-5')
AUTH_EMAIL_ENABLED = os.getenv('AUTH_EMAIL_ENABLED', 'False').lower() == 'true'
NOTIFICATION_EMAIL_ENABLED = os.getenv('NOTIFICATION_EMAIL_ENABLED', 'False').lower() == 'true'
# 只从部署环境读取密钥，不通过参数管理或匿名能力接口回显。
import json
try:
    NOTIFICATION_EXTERNAL_CHANNELS = json.loads(os.getenv('ADMINCORE_NOTIFICATION_EXTERNAL_CHANNELS_JSON', '{}'))
    if not isinstance(NOTIFICATION_EXTERNAL_CHANNELS, dict):
        raise ValueError()
except (ValueError, TypeError):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('ADMINCORE_NOTIFICATION_EXTERNAL_CHANNELS_JSON 必须为 JSON 对象') from None
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower() == 'true'
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '10'))
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', '')
if AUTH_EMAIL_ENABLED or NOTIFICATION_EMAIL_ENABLED:
    from django.core.exceptions import ImproperlyConfigured, ValidationError
    from django.core.validators import validate_email
    try:
        validate_email(DEFAULT_FROM_EMAIL)
    except ValidationError:
        raise ImproperlyConfigured('启用邮件需配置有效的 DEFAULT_FROM_EMAIL') from None
    if (not EMAIL_HOST or any(char.isspace() for char in EMAIL_HOST) or not 1 <= EMAIL_PORT <= 65535
            or EMAIL_USE_TLS == EMAIL_USE_SSL or not 1 <= EMAIL_TIMEOUT <= 30):
        raise ImproperlyConfigured('邮件需要 SMTP 主机、有效端口、单选 TLS/SSL 及 1-30 秒超时')
if not (60 <= AUTH_SESSION_TOUCH_SECONDS <= AUTH_SESSION_IDLE_SECONDS <= AUTH_SESSION_ABSOLUTE_SECONDS
        <= 30 * 86400):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('会话期限需满足 60 ≤ 活动登记间隔 ≤ 空闲期限 ≤ 绝对期限 ≤ 30 天')

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
CORS_EXPOSE_HEADERS = ['X-Request-ID', 'Idempotency-Replayed', 'X-API-Version', 'Deprecation', 'Sunset', 'Link']

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
ADMINCORE_BACKUP_ENABLED = os.getenv('ADMINCORE_BACKUP_ENABLED', 'False').lower() == 'true'
try:
    ADMINCORE_BACKUP_RETENTION_DAYS = int(os.getenv('ADMINCORE_BACKUP_RETENTION_DAYS', '30'))
    ADMINCORE_BACKUP_RETENTION_COUNT = int(os.getenv('ADMINCORE_BACKUP_RETENTION_COUNT', '7'))
    if not (1 <= ADMINCORE_BACKUP_RETENTION_DAYS <= 3650 and 1 <= ADMINCORE_BACKUP_RETENTION_COUNT <= 1000):
        raise ValueError()
except ValueError:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('备份保留天数须为 1–3650，最少保留份数须为 1–1000') from None

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
if (set(ADMINCORE_MODULES) <= {'realtime'} or
        (ADMINCORE_PRESET == 'minimal' and set(ADMINCORE_MODULES) <= {'realtime', 'system', 'example', 'files', 'feature_flags', 'ip_policy'})):
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# 默认只输出控制台，由部署平台有界轮转，避免多个 worker 竞争同一文件。
# 受信任的单进程终端部署可显式开启文件日志。
DJANGO_FILE_LOGGING = os.getenv('DJANGO_FILE_LOGGING', 'False').lower() == 'true'
LOG_DIR = os.path.join(BASE_DIR, 'logs')
if DJANGO_FILE_LOGGING:
    os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            '()': 'apps.core.runtime_logging.SafeJSONFormatter',
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
        'handlers': ['console', *(['file'] if DJANGO_FILE_LOGGING else [])],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', *(['file'] if DJANGO_FILE_LOGGING else [])],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}

if not DJANGO_FILE_LOGGING:
    LOGGING['handlers'].pop('file')

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
