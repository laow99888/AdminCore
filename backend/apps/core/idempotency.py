"""幂等记录与业务写入共用事务；鉴权必须在进入本入口之前执行。"""
import hashlib
import json
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from .models import IdempotencyRecord

IDEMPOTENT_WRITE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})


class IdempotencyConflict(APIException):
    status_code = 409
    default_detail = '幂等键已用于另一份请求'
    default_code = 'idempotency_conflict'


def with_idempotency(request, scope, callback, ttl_hours=24):
    """成功结果保存 24 小时；失败整体回滚，同键可以重试。"""
    raw_key = request.headers.get('Idempotency-Key')
    if raw_key is None:
        with transaction.atomic():
            return callback()
    if not raw_key or len(raw_key) > 128 or any(ord(char) < 33 or ord(char) > 126 for char in raw_key):
        raise ValidationError('Idempotency-Key 必须是 1-128 个无空格的 ASCII 字符')
    if (
        request.method not in IDEMPOTENT_WRITE_METHODS
        or not request.user.is_authenticated
        or request.content_type != 'application/json'
    ):
        raise ValidationError('幂等请求仅支持已登录的 JSON 写操作')
    body = json.dumps(request.data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(f'{request.method}|{request.get_full_path()}|{body}'.encode()).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        record, created = IdempotencyRecord.objects.get_or_create(
            actor=request.user, scope=scope, key=raw_key,
            defaults={'request_hash': digest, 'expires_at': now + timedelta(hours=ttl_hours)},
        )
        record = IdempotencyRecord.objects.select_for_update().get(pk=record.pk)
        if not created and record.expires_at > now:
            if record.request_hash != digest:
                raise IdempotencyConflict('同一幂等键不能用于不同请求')
            if record.status == 'succeeded':
                return Response(record.response_data, status=record.response_status,
                                headers={'Idempotency-Replayed': 'true'})
            raise IdempotencyConflict('相同请求正在处理中，请稍后重试')
        response = callback()
        if response.status_code >= 400:
            transaction.set_rollback(True)
            return response
        record.request_hash = digest
        record.expires_at = now + timedelta(hours=ttl_hours)
        record.response_data = json.loads(JSONRenderer().render(response.data))
        record.response_status = response.status_code
        record.status = 'succeeded'
        record.save(update_fields=['request_hash', 'expires_at', 'response_data', 'response_status', 'status', 'updated_at'])
        return response
