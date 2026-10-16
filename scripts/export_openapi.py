"""离线导出确定性的实际 URL 契约；隔离部署环境，不读取 .env 或连接业务数据库。"""
import argparse
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['full', 'standard', 'minimal'], default='full')
    parser.add_argument('--modules', help='显式覆盖模块列表；依赖/未知模块由现有契约验证')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    # 导出是开发工具；不继承任何部署密钥、供应商配置、数据库或生命周期时间窗口。
    for key in list(os.environ):
        if key.startswith(('ADMINCORE_', 'AUTH_', 'DJANGO_', 'DB_', 'SSO_', 'CELERY_', 'REDIS_', 'EMAIL_', 'SMTP_', 'AWS_')):
            del os.environ[key]
    os.environ.update(PYTHON_DOTENV_DISABLED='1', DJANGO_SETTINGS_MODULE='config.settings.testing',
                      DJANGO_ENV='testing', PYTHONUTF8='1', ADMINCORE_PRESET='standard')
    sys.path.insert(0, str(ROOT / 'backend'))
    from apps.core.modules import MODULES
    if args.modules is not None:
        os.environ['ADMINCORE_MODULES'] = args.modules
    elif args.profile == 'full':
        os.environ['ADMINCORE_MODULES'] = ','.join(module.key for module in MODULES)
    elif args.profile == 'minimal':
        os.environ['ADMINCORE_PRESET'] = 'minimal'
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    media = Path(settings.MEDIA_ROOT).resolve()
    try:
        with tempfile.TemporaryDirectory(prefix='admincore-openapi-') as temporary:
            raw = Path(temporary) / 'schema.json'
            call_command('spectacular', format='openapi-json', file=str(raw), validate=True,
                         fail_on_warn=True, stdout=StringIO())
            schema = json.loads(raw.read_text(encoding='utf-8'))
        schema['info']['x-admincore-modules'] = list(settings.ADMINCORE_MODULES)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
                               encoding='utf-8', newline='\n')
        print(json.dumps({'paths': len(schema['paths']), 'modules': list(settings.ADMINCORE_MODULES)}))
    finally:
        # testing.py 在本进程中创建的空临时媒体目录；不触碰部署媒体或已有用户文件。
        if media.parent == Path(tempfile.gettempdir()).resolve() and media.name.startswith('admincore-test-media-'):
            shutil.rmtree(media)


if __name__ == '__main__':
    main()
