"""部署级存储配置；桶、凭据与对象键前缀不通过管理 API 修改。"""
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def storage_settings(environment):
    mode = environment.get('ADMINCORE_STORAGE_BACKEND', 'local')
    default = {'BACKEND': 'django.core.files.storage.FileSystemStorage'}
    if mode == 's3':
        bucket = environment.get('S3_BUCKET_NAME', '')
        access = environment.get('S3_ACCESS_KEY_ID', '')
        secret = environment.get('S3_SECRET_ACCESS_KEY', '')
        prefix = environment.get('S3_LOCATION', 'admincore').strip('/')
        if not bucket or not access or not secret:
            raise ImproperlyConfigured('S3 存储需要 bucket、access key 和 secret key')
        if (not prefix or '\\' in prefix or any(part in ('', '.', '..') for part in prefix.split('/'))
                or any(ord(char) < 32 for char in prefix)):
            raise ImproperlyConfigured('S3_LOCATION 必须是非空的安全对象键前缀')
        endpoint = environment.get('S3_ENDPOINT_URL') or None
        if endpoint:
            parsed = urlsplit(endpoint)
            if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password
                    or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
                raise ImproperlyConfigured('S3_ENDPOINT_URL 必须是无凭据、路径和查询参数的 HTTP(S) 地址')
            if parsed.scheme == 'http' and environment.get('S3_ALLOW_INSECURE_HTTP', 'False').lower() != 'true':
                raise ImproperlyConfigured('HTTP 对象存储须明确设置 S3_ALLOW_INSECURE_HTTP=True')
        style = environment.get('S3_ADDRESSING_STYLE', 'path')
        if style not in ('path', 'virtual'):
            raise ImproperlyConfigured('S3_ADDRESSING_STYLE 仅支持 path 或 virtual')
        from botocore.config import Config
        default = {'BACKEND': 'storages.backends.s3.S3Storage', 'OPTIONS': {
            'bucket_name': bucket, 'access_key': access, 'secret_key': secret,
            'endpoint_url': endpoint, 'region_name': environment.get('S3_REGION_NAME', 'us-east-1'),
            'location': prefix, 'default_acl': None, 'querystring_auth': True,
            'querystring_expire': 300, 'file_overwrite': False, 'max_memory_size': 8 * 1024 * 1024,
            'client_config': Config(signature_version='s3v4', s3={'addressing_style': style},
                                    connect_timeout=5, read_timeout=30,
                                    retries={'mode': 'standard', 'max_attempts': 3}),
        }}
    elif mode != 'local':
        raise ImproperlyConfigured('ADMINCORE_STORAGE_BACKEND 仅支持 local 或 s3')
    return {'default': default, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
