"""普通上传和分片上传共用的元数据校验。"""
import os

from django.conf import settings
from rest_framework.exceptions import ValidationError


def validate_upload_metadata(name, size):
    from apps.core.error_i18n import error_text
    extension = os.path.splitext(name)[1].lower().lstrip('.')
    allowed = [value.lower() for value in getattr(settings, 'FILE_UPLOAD_ALLOWED_EXTENSIONS', [])]
    if allowed and extension not in allowed:
        raise ValidationError(error_text('不支持的文件类型 ".{extension}"，允许的类型：{allowed}',
                                        extension=extension, allowed=', '.join(allowed)))
    maximum = getattr(settings, 'FILE_UPLOAD_MAX_SIZE', 50 * 1024 * 1024)
    if size <= 0:
        raise ValidationError('不允许上传空文件')
    if size > maximum:
        raise ValidationError(error_text('文件大小超出限制（最大 {megabytes}MB）', megabytes=maximum // (1024 * 1024)))
    return extension
