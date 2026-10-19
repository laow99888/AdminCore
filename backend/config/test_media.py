"""测试 settings 独立使用时也回收自己的媒体；pytest 失败可显式保留。"""
import atexit
import shutil
import tempfile
from pathlib import Path

_roots = set()
_preserved = set()


def create_test_media():
    root = Path(tempfile.mkdtemp(prefix='admincore-test-media-')).resolve()
    _roots.add(root)
    return str(root)


def preserve_test_media(root):
    _preserved.add(Path(root).resolve())


@atexit.register
def cleanup_test_media():
    for root in _roots - _preserved:
        if root.parent == Path(tempfile.gettempdir()).resolve() and root.name.startswith('admincore-test-media-'):
            shutil.rmtree(root, ignore_errors=True)
