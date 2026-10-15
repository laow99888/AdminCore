"""镜像内固定构建能力；环境变量不能将精简镜像升级成完整镜像。"""
import json
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


MARKER = Path(__file__).with_name('build-profile.json')


def load_profile(marker=MARKER):
    # 源码工作区沿用完整依赖；Docker 构建始终写入固定标记。
    if not marker.exists():
        return 'full'
    try:
        value = json.loads(marker.read_text(encoding='utf-8'))
        if value not in ({'profile': 'full'}, {'profile': 'minimal'}):
            raise ValueError('unknown_profile')
        return value['profile']
    except (OSError, ValueError):
        raise ImproperlyConfigured('镜像构建能力标记无效，请重新构建镜像') from None


def validate_profile(profile, modules, storage='local', image_processing=False):
    if profile not in ('full', 'minimal'):
        raise ImproperlyConfigured('不支持的镜像构建能力')
    if profile == 'minimal' and (modules or storage != 'local' or image_processing):
        raise ImproperlyConfigured(
            '精简镜像仅包含核心模块和本地存储；启用可选模块、S3或图片处理前，'
            '请移除精简构建覆盖并重新构建完整镜像，保留原数据卷')
