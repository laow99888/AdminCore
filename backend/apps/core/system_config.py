"""业务参数白名单与带版本缓存。每次读取版本，跨 API/worker 不依赖缓存失效广播。"""
from dataclasses import dataclass
from django.conf import settings
from django.core.cache import cache
from rest_framework import serializers
from .models import SystemConfig
from .modules import module_enabled


def validate_logo(value):
    import base64
    import binascii
    import io
    import warnings
    from PIL import Image, UnidentifiedImageError
    if value == '':
        return ''
    if not isinstance(value, str) or len(value) > 280000:
        raise serializers.ValidationError({'value': 'Logo 最大 200 KB'})
    prefix, separator, encoded = value.partition(',')
    if not separator or prefix not in ('data:image/png;base64', 'data:image/jpeg;base64', 'data:image/webp;base64'):
        raise serializers.ValidationError({'value': 'Logo 仅支持 PNG、JPEG 或 WebP 图片'})
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 200 * 1024:
            raise ValueError('too large')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ('PNG', 'JPEG', 'WEBP') or max(image.size) > 1024:
                    raise ValueError('invalid format or dimensions')
                image.load()
                pixels = image.convert('RGBA')
                pixels.thumbnail((256, 256))
                output = io.BytesIO()
                # 从像素重新生成，清除 EXIF、脚本及其他元数据；不接受外部地址。
                clean = Image.frombytes('RGBA', pixels.size, pixels.tobytes())
                clean.save(output, format='PNG', optimize=True)
                if output.tell() > 200 * 1024:
                    clean.thumbnail((128, 128))
                    output = io.BytesIO()
                    clean.save(output, format='PNG', optimize=True)
        return 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode('ascii')
    except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise serializers.ValidationError({'value': 'Logo 图片无效或尺寸超过 1024 × 1024'}) from exc


@dataclass(frozen=True)
class ConfigDefinition:
    key: str
    label: str
    kind: str
    default: object
    setting: str = ''
    minimum: int = 0
    maximum: int = 100

    def default_value(self):
        return getattr(settings, self.setting, self.default) if self.setting else self.default

    def validate(self, value):
        if self.kind == 'image':
            return validate_logo(value)
        if self.kind == 'integer':
            if type(value) is not int or not self.minimum <= value <= self.maximum:
                raise serializers.ValidationError({'value': f'必须为 {self.minimum}–{self.maximum} 的整数'})
        elif not isinstance(value, str) or not self.minimum <= len(value.strip()) <= self.maximum:
            raise serializers.ValidationError({'value': f'文本长度必须为 {self.minimum}–{self.maximum}'})
        return value.strip() if isinstance(value, str) else value


CONFIG_DEFINITIONS = {definition.key: definition for definition in (
    ConfigDefinition('brand.name', '产品名称', 'string', 'AdminCore', minimum=1, maximum=40),
    ConfigDefinition('brand.tagline', '登录页说明', 'string', '现代化中后台管理系统', minimum=0, maximum=120),
    ConfigDefinition('brand.logo', '产品 Logo', 'image', '', minimum=0, maximum=280000),
    ConfigDefinition('files.retention_days', '软删除文件保留天数', 'integer', 30, 'FILE_SOFT_DELETE_RETENTION_DAYS', 1, 3650),
    ConfigDefinition('notifications.retention_days', '已读通知保留天数', 'integer', 90, 'NOTIFICATION_RETENTION_DAYS', 1, 3650),
)}


def config_value(key):
    definition = CONFIG_DEFINITIONS[key]
    if not module_enabled('system'):
        return definition.default_value()
    row = SystemConfig.objects.filter(key=key).only('id', 'value', 'version').first()
    if row is None:
        return definition.default_value()
    cache_key = f'admincore:config:{row.id}:v{row.version}'
    value = cache.get(cache_key)
    if value is None:
        value = definition.validate(row.value)
        cache.set(cache_key, value, timeout=300)
    return value
