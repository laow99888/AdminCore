"""有界图片变换：原件只读，首帧、去元数据、保持比例，结果仅在内存中。"""
import hashlib
import io
import warnings

from django.conf import settings
from PIL import Image, ImageOps

from apps.core.exceptions import APIError
from .preview import IMAGE_FORMATS

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_WATERMARK_BYTES = 512 * 1024
MAX_WATERMARK_PIXELS = 1_000_000
FORMATS = {'png': ('PNG', 'image/png'), 'jpeg': ('JPEG', 'image/jpeg'), 'webp': ('WEBP', 'image/webp')}


class BoundedOutput(io.BytesIO):
    def write(self, content):
        if self.tell() + len(content) > MAX_BYTES:
            raise APIError('图片处理结果超过 10 MiB，请缩小尺寸', status_code=413)
        return super().write(content)


def _decode(content, *, expected=None, watermark=False):
    limit = MAX_WATERMARK_PIXELS if watermark else MAX_PIXELS
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(content)) as source:
            if (expected and source.format != expected) or (watermark and source.format not in {'PNG', 'JPEG', 'WEBP'}):
                raise ValueError('unsupported or mismatched image')
            if source.width * source.height > limit or (watermark and max(source.size) > 1024):
                raise APIError('水印图片最大 1024px / 100 万像素' if watermark else '图片最大 1600 万像素', status_code=413)
            source.verify()
        with Image.open(io.BytesIO(content)) as source:
            source.seek(0)
            result = ImageOps.exif_transpose(source).convert('RGBA')
            # convert 会继承 info；显式清空，防止编码器重新写入 EXIF/ICC/注释。
            result.info.clear()
            return result


def transform_content(instance, options):
    extension = instance.file_type.lower()
    if extension not in IMAGE_FORMATS:
        raise APIError('此类型不支持图片处理', status_code=415)
    if instance.size > MAX_BYTES:
        raise APIError('图片处理仅支持 10 MiB 内的原件', status_code=413)
    try:
        with instance.file.open('rb') as stream:
            content = stream.read(MAX_BYTES + 1)
    except FileNotFoundError as exc:
        raise APIError('文件不存在', status_code=404) from exc
    except APIError:
        raise
    except Exception as exc:
        raise APIError('存储暂时不可用，请稍后重试', status_code=503) from exc
    if len(content) > MAX_BYTES:
        raise APIError('图片处理仅支持 10 MiB 内的原件', status_code=413)
    watermark_digest = None
    try:
        image = _decode(content, expected=IMAGE_FORMATS[extension])
        try:
            image.thumbnail((options['width'], options['height']), Image.Resampling.LANCZOS)
            watermark = options.get('watermark')
            if watermark is not None:
                watermark.seek(0)
                mark_bytes = watermark.read(MAX_WATERMARK_BYTES + 1)
                if len(mark_bytes) > MAX_WATERMARK_BYTES:
                    raise APIError('水印图片最大 512 KiB', status_code=413)
                mark = _decode(mark_bytes, watermark=True)
                try:
                    # 水印最多占成品宽/高的四分之一，不放大小图。
                    mark.thumbnail((max(1, image.width // 4), max(1, image.height // 4)), Image.Resampling.LANCZOS)
                    alpha = mark.getchannel('A').point(lambda value: value * options['opacity'] // 100)
                    mark.putalpha(alpha)
                    alpha.close()
                    if options['position'] == 'center':
                        xy = ((image.width - mark.width) // 2, (image.height - mark.height) // 2)
                    else:
                        padding = min(12, max(0, min(image.size) // 20))
                        xy = (max(0, image.width - mark.width - padding), max(0, image.height - mark.height - padding))
                    image.alpha_composite(mark, dest=xy)
                    watermark_digest = hashlib.sha256(mark_bytes).hexdigest()
                finally:
                    mark.close()
            output = BoundedOutput()
            kind, content_type = FORMATS[options['format']]
            encode = {} if kind == 'PNG' else {'quality': options['quality']}
            if kind == 'JPEG':
                flattened = Image.new('RGB', image.size, 'white')
                try:
                    flattened.paste(image, mask=image.getchannel('A'))
                    flattened.save(output, format=kind, **encode)
                finally:
                    flattened.close()
            else:
                image.save(output, format=kind, **encode)
            result = output.getvalue()
            projection = {
                'id': str(instance.pk), 'lifecycle_version': instance.lifecycle_version,
                'source_sha256': hashlib.sha256(content).hexdigest(), 'width': image.width, 'height': image.height,
                'format': options['format'], 'quality': options['quality'] if kind != 'PNG' else None,
                'watermark_sha256': watermark_digest, 'opacity': options['opacity'] if watermark_digest else None,
                'position': options['position'] if watermark_digest else None,
                'output_sha256': hashlib.sha256(result).hexdigest(), 'size': len(result),
            }
            return result, content_type, projection
        finally:
            image.close()
    except APIError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise APIError('图片像素超出处理限制', status_code=413) from exc
    except Exception as exc:
        raise APIError('图片内容损坏或类型不符，无法处理', status_code=422) from exc


def processing_config():
    return {'enabled': settings.ADMINCORE_IMAGE_PROCESSING_ENABLED, 'max_bytes': MAX_BYTES,
            'max_pixels': MAX_PIXELS, 'max_dimension': 4096, 'watermark_max_bytes': MAX_WATERMARK_BYTES,
            'formats': list(FORMATS)}
