"""管理入口统一脱敏；原值仅通过显式授权的单对象密码确认接口返回。"""
import re

from rest_framework import serializers


def mask_phone(value):
    if not value:
        return ''
    digits = re.sub(r'\D', '', str(value))
    return digits[:3] + '****' + digits[-4:] if len(digits) >= 11 else '****'


def mask_email(value):
    if not value:
        return ''
    local, separator, domain = str(value).rpartition('@')
    if not separator or not local or not domain:
        return '***'
    return (local[:1] if len(local) > 1 else '') + '***@' + domain


def validate_contact_email(value):
    # '*' 合法于某些邮件地址，但这里保留为脱敏标记，避免误存页面显示值。
    if '*' in value:
        raise serializers.ValidationError('请填写新的完整邮箱，不能提交脱敏值')
    return value


def phone_input_field():
    return serializers.RegexField(r'^\+?[0-9 ()-]{3,20}$', required=False,
                                  allow_blank=True, max_length=20)


class MaskedContactSerializerMixin:
    def to_representation(self, instance):
        result = super().to_representation(instance)
        for field, mask in (('email', mask_email), ('phone', mask_phone)):
            if field in result:
                result[field] = mask(result[field])
        return result

    def validate_email(self, value):
        return validate_contact_email(value)
