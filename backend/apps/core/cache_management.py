"""Bounded cleanup of registered current-version keys; never Redis scans or flush."""
import hashlib
import json

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from apps.logs.models import OperationLog
from apps.permissions.permissions import has_permission_code
from .cache_keys import config_cache_key, dictionary_cache_key
from .models import SystemConfig, DataDictionary
from .system_config import CONFIG_DEFINITIONS

NAMESPACES = {'configuration': 'config:update', 'dictionaries': 'dictionary:update'}
LIMIT = 1000
MAX_AGE = 120
SALT = 'admincore-cache-preview-v1'


class CacheConflict(APIException):
    status_code = 409
    default_detail = '预览已过期或范围已变化，请重新预览'


class CacheUnavailable(APIException):
    status_code = 503
    default_detail = '清理未确认，可能部分完成，请重新预览后重试'


def backend_mode():
    backend = settings.CACHES['default']['BACKEND']
    return {'django_redis.cache.RedisCache': 'shared',
            'django.core.cache.backends.locmem.LocMemCache': 'in_process'}.get(backend, 'unsupported')


def candidates(namespace):
    if namespace not in NAMESPACES:
        raise ValidationError({'namespace': '命名空间未登记'})
    if namespace == 'configuration':
        rows = SystemConfig.objects.filter(key__in=CONFIG_DEFINITIONS).order_by('id').values_list('id', 'version')
        key = config_cache_key
    else:
        rows = DataDictionary.objects.order_by('id').values_list('id', 'version')
        key = dictionary_cache_key
    return [key(identifier, version) for identifier, version in rows[:LIMIT + 1]]


def snapshot(namespace):
    keys = candidates(namespace)
    return keys, hashlib.sha256(json.dumps(keys).encode()).hexdigest()


def authorize(request, namespace):
    if not has_permission_code(request.user, NAMESPACES[namespace]):
        raise PermissionDenied()
    if backend_mode() == 'unsupported':
        raise CacheUnavailable('当前缓存后端不支持此清理入口')


def preview(request, namespace):
    authorize(request, namespace)
    keys, digest = snapshot(namespace)
    if len(keys) > LIMIT:
        raise ValidationError({'namespace': '候选数量超过单次 1000 项上限，此入口拒绝清理'})
    token = signing.dumps({'user': str(request.user.pk), 'session': request.user.session_version,
                           'namespace': namespace, 'digest': digest, 'backend': backend_mode()}, salt=SALT)
    return {'namespace': namespace, 'candidate_count': len(keys), 'backend': backend_mode(),
            'expires_in': MAX_AGE, 'token': token}


def clear(request, namespace, token):
    authorize(request, namespace)
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature as exc:
        raise CacheConflict() from exc
    keys, digest = snapshot(namespace)
    expected = {'user': str(request.user.pk), 'session': request.user.session_version,
                'namespace': namespace, 'digest': digest, 'backend': backend_mode()}
    if data != expected or len(keys) > LIMIT:
        raise CacheConflict()
    # Persist an uncertain outcome BEFORE touching the separate cache service.
    audit_data = {'namespace': namespace, 'candidate_count': len(keys), 'backend': backend_mode(), 'outcome': 'unconfirmed'}
    log = OperationLog.objects.create(user=request.user, action='delete', resource='business_cache',
                                     resource_id=namespace, status=503, description=json.dumps(audit_data),
                                     ip_address=request.META.get('REMOTE_ADDR') or '127.0.0.1')
    try:
        if keys:
            result = cache.delete_many(keys)
            # django-redis may suppress connection errors if a deployment enables
            # IGNORE_EXCEPTIONS; its successful delete_many always returns an int.
            if backend_mode() == 'shared' and type(result) is not int:
                raise CacheUnavailable()
    except Exception as exc:
        raise CacheUnavailable() from exc
    audit_data['outcome'] = 'completed'
    try:
        log.status, log.description = 200, json.dumps(audit_data)
        log.save(update_fields=['status', 'description'])
    except Exception as exc:
        raise CacheUnavailable() from exc
    return {'namespace': namespace, 'candidate_count': len(keys), 'backend': backend_mode(), 'outcome': 'completed'}
