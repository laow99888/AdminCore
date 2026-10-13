"""通过当前 Django 存储导出媒体，不要求对象存储提供本地路径。"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.core.files.storage import default_storage
from apps.core.media_storage import export_media

if __name__ == '__main__':
    export_media(default_storage, sys.stdout.buffer)
