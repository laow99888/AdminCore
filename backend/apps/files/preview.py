"""私有文件预览：有限读取、内容验证；图片重新编码，PDF 禁止主动内容。"""

import io
import warnings

from django.conf import settings
from PIL import Image
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

from apps.core.exceptions import APIError

IMAGE_FORMATS = {'jpg': 'JPEG', 'jpeg': 'JPEG', 'png': 'PNG', 'gif': 'GIF',
                 'webp': 'WEBP', 'bmp': 'BMP', 'ico': 'ICO'}
FORBIDDEN_KEYS = {'/AA', '/OpenAction', '/JS', '/JavaScript', '/EmbeddedFiles', '/EF',
                  '/XFA', '/AcroForm', '/RichMediaContent', '/3DD'}
FORBIDDEN_ACTIONS = {'/JavaScript', '/Launch', '/URI', '/GoToR', '/GoToE', '/SubmitForm',
                     '/ImportData', '/Rendition', '/Movie', '/Sound'}


def _pdf(content):
    if not content.startswith(b'%PDF-') or not content.rstrip().endswith(b'%%EOF'):
        raise ValueError('invalid PDF boundary')
    reader = PdfReader(io.BytesIO(content), strict=True)
    if reader.is_encrypted:
        raise APIError('加密 PDF 暂不支持预览', status_code=415)
    # 遍历有界对象图；不解压页面内容流、不执行动作、不跟随外部资源。
    pending, seen, visited = [(reader.trailer, 0)], set(), 0
    while pending:
        obj, depth = pending.pop()
        visited += 1
        if visited > 20_000 or depth > 100:
            raise APIError('PDF 结构过于复杂，暂不支持预览', status_code=413)
        if isinstance(obj, IndirectObject):
            key = ('ref', obj.idnum, obj.generation)
            if key in seen:
                continue
            seen.add(key)
            obj = obj.get_object()
        if isinstance(obj, (DictionaryObject, ArrayObject)):
            key = ('object', id(obj))
            if key in seen:
                continue
            seen.add(key)
        if isinstance(obj, DictionaryObject):
            # DictionaryObject 下标会解析间接引用，不能只检查原始引用对象。
            action = obj['/S'] if '/S' in obj else None
            kind = obj['/Type'] if '/Type' in obj else None
            subtype = obj['/Subtype'] if '/Subtype' in obj else None
            if (FORBIDDEN_KEYS.intersection(obj) or action in FORBIDDEN_ACTIONS
                    or kind == '/EmbeddedFile'
                    or subtype in {'/RichMedia', '/Movie', '/Sound', '/FileAttachment', '/Screen', '/Widget', '/3D'}):
                raise APIError('含脚本、附件、表单或外部动作的 PDF 暂不支持预览', status_code=415)
            pending.extend((value, depth + 1) for value in obj.values())
        elif isinstance(obj, ArrayObject):
            pending.extend((value, depth + 1) for value in obj)
    pages = len(reader.pages)
    if not 0 < pages <= settings.FILE_PREVIEW_MAX_PDF_PAGES:
        raise APIError('PDF 页数超出预览限制', status_code=413)
    for page in reader.pages:
        box = page.mediabox
        if not (0 < float(box.width) <= 14_400 and 0 < float(box.height) <= 14_400):
            raise APIError('PDF 页面尺寸超出预览限制', status_code=413)
    return content, 'application/pdf'


def _image(content, extension):
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(content)) as image:
            if image.format != IMAGE_FORMATS[extension]:
                raise ValueError('extension and content differ')
            if image.width * image.height > settings.FILE_PREVIEW_MAX_PIXELS:
                raise APIError('图片像素超出预览限制', status_code=413)
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            # 动图/多帧仅显示第一帧，清除 EXIF、注释等元数据及附加内容。
            image.seek(0)
            output = io.BytesIO()
            image.convert('RGBA').save(output, format='PNG')
    if output.tell() > settings.FILE_PREVIEW_MAX_SIZE:
        raise APIError('图片解码结果超出预览限制', status_code=413)
    return output.getvalue(), 'image/png'


def preview_content(instance):
    extension = instance.file_type.lower()
    if extension not in IMAGE_FORMATS and extension != 'pdf':
        raise APIError('此类型暂不支持预览，请下载查看', status_code=415)
    limit = settings.FILE_PREVIEW_MAX_SIZE
    if instance.size > limit:
        raise APIError('文件超过 10 MiB 预览限制，请下载查看', status_code=413)
    try:
        # 不使用 .path；本地和 S3 都从 storage 流有限读取。
        with instance.file.open('rb') as stream:
            content = stream.read(limit + 1)
    except FileNotFoundError as exc:
        raise APIError('文件不存在', status_code=404) from exc
    except APIError:
        raise
    except Exception as exc:
        raise APIError('存储暂时不可用，请稍后重试', status_code=503) from exc
    if len(content) > limit:
        raise APIError('文件超过 10 MiB 预览限制，请下载查看', status_code=413)
    try:
        return _pdf(content) if extension == 'pdf' else _image(content, extension)
    except APIError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise APIError('图片像素超出预览限制', status_code=413) from exc
    except Exception as exc:
        # 解析器异常仅转为固定文案，不能泄露对象存储信息或文档内容。
        raise APIError('文件内容损坏或与扩展名不符，无法预览', status_code=422) from exc
