"""可选手机号存储加密；密钥存在即加密写入，不提供自动解密降级。"""
import re

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import DatabaseError, models
from django.db.models import Case, Value
from django.db.models.functions import Cast
from rest_framework.exceptions import APIException

PREFIX = 'enc:phone:v1:'
NAMESPACE = b'admincore:phone:v1:'
PHONE_PATTERN = r'^\+?[0-9 ()-]{3,20}$'


class FieldEncryptionUnavailable(APIException):
    status_code = 503
    default_detail = '敏感字段暂不可用，请联系管理员'
    default_code = 'field_encryption_unavailable'


class _DecryptedPhone(str):
    """标记来自密文的值；移除密钥后旧对象保存也必须失败关闭。"""


def field_cipher():
    try:
        key = getattr(settings, 'ADMINCORE_FIELD_ENCRYPTION_KEY', '')
        return Fernet(key.encode('ascii') if isinstance(key, str) else key)
    except (ValueError, TypeError, UnicodeError):
        raise FieldEncryptionUnavailable() from None


def validate_phone(value):
    if not isinstance(value, str) or len(value) > 20 or (value and re.fullmatch(PHONE_PATTERN, value) is None):
        raise ValidationError('手机号格式无效', code='invalid_phone')
    return value


class EncryptedPhoneField(models.CharField):
    default_validators = [RegexValidator(PHONE_PATTERN, '手机号格式无效', code='invalid_phone')]

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 20)
        super().__init__(*args, **kwargs)

    def db_type(self, connection):
        # API/form 仍使用 max_length=20，数据库需容纳带版本前缀的 Fernet 密文。
        return models.TextField().db_type(connection)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        if not value.startswith(PREFIX):
            return value  # 存量明文兼容读取；转换命令会报告非法存量值。
        try:
            payload = field_cipher().decrypt(value[len(PREFIX):].encode('ascii'))
            if not payload.startswith(NAMESPACE):
                raise InvalidToken()
            phone = payload[len(NAMESPACE):].decode('utf-8')
            validate_phone(phone)
            return _DecryptedPhone(phone)
        except (InvalidToken, UnicodeError, ValidationError, ValueError):
            raise FieldEncryptionUnavailable() from None

    def get_prep_value(self, value):
        validate_phone(value)
        needs_cipher = (getattr(settings, 'ADMINCORE_FIELD_ENCRYPTION_ENABLED', False)
                        or bool(getattr(settings, 'ADMINCORE_FIELD_ENCRYPTION_KEY', ''))
                        or isinstance(value, _DecryptedPhone))
        if not value:
            return ''
        if needs_cipher:
            return PREFIX + field_cipher().encrypt(NAMESPACE + value.encode('utf-8')).decode('ascii')
        return str(value)

    def get_db_prep_save(self, value, connection):
        if hasattr(value, 'resolve_expression'):
            return self._prepare_expression(value, connection)
        self._prevent_plaintext_downgrade(value, connection)
        return self.get_prep_value(value)

    def _prevent_plaintext_downgrade(self, value, connection):
        if not value or getattr(settings, 'ADMINCORE_FIELD_ENCRYPTION_KEY', '') or getattr(settings, 'ADMINCORE_FIELD_ENCRYPTION_ENABLED', False):
            return
        # 持久数据决定保护模式；撤 key 后 known-pk update/bulk 不可覆写旧密文为明文。
        table = connection.ops.quote_name(self.model._meta.db_table)
        column = connection.ops.quote_name(self.column)
        try:
            with connection.cursor() as cursor:
                cursor.execute(f'SELECT 1 FROM {table} WHERE {column} LIKE %s LIMIT 1', [PREFIX + '%'])
                if cursor.fetchone():
                    raise FieldEncryptionUnavailable()
        except DatabaseError:
            raise FieldEncryptionUnavailable() from None

    def _prepare_expression(self, expression, connection):
        # bulk_update 的 Case/Value 路径也必须加密；拒绝 F/RawSQL 等数据库内明文运算。
        if isinstance(expression, Value):
            self._prevent_plaintext_downgrade(expression.value, connection)
            value = None if expression.value is None else self.get_prep_value(expression.value)
            return Value(value, output_field=models.TextField())
        if isinstance(expression, Case):
            result = expression.copy()
            result.cases = []
            for case in expression.cases:
                branch = case.copy()
                branch.result = self._prepare_expression(case.result, connection)
                result.cases.append(branch)
            result.default = self._prepare_expression(expression.default, connection)
            result.output_field = models.TextField()
            return result
        if isinstance(expression, Cast):
            return Cast(self._prepare_expression(expression.get_source_expressions()[0], connection), models.TextField())
        raise ValidationError('手机号不支持数据库表达式写入', code='invalid_phone_expression')
