"""
测试环境配置
"""

import tempfile

from .base import *

DEBUG = True
TESTING = True

# 使用内存数据库加快测试
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# 媒体文件写入临时目录，避免测试产物污染仓库
MEDIA_ROOT = tempfile.mkdtemp(prefix='admincore-test-media-')

# 缓存使用进程内实现：避免测试把限流计数写进真实 Redis，影响开发环境
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# 任务同步执行（无需 Redis/worker），异常直接抛出便于测试断言
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# 禁用密码校验加速测试
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# 关闭日志
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
}
