"""创建、启动和重置独立本机演示项目；不接管现有数据库，不自动删除资源。"""
import argparse
import json
from pathlib import Path
import secrets
import subprocess
import uuid

from create_project import (ROOT, ProjectError, create_project, load_project,
                            compose_command, verify_ownership, run_project)

DEMO_META = 'admincore.demo.json'


def create_demo(target, *, source=ROOT, ref='HEAD', frontend_port=8088, backend_port=8008):
    instance = uuid.uuid4().hex
    name = 'admincore-demo-' + instance[:16]
    metadata = create_project(target, source=source, ref=ref, name=name, preset='standard',
                              frontend_port=frontend_port, backend_port=backend_port)
    root = Path(target).resolve()
    needed = ('backend/config/settings/demo.py',
              'backend/apps/core/management/commands/demo_admincore.py', 'scripts/demo_project.py')
    if any(not (root / path).is_file() for path in needed):
        raise ProjectError('源提交不包含完整演示能力；保留已导出的目录，请选择包含演示功能的新提交')
    replacements = {
        'DB_NAME': 'admincore_demo_' + instance, 'DJANGO_ENV': 'demo',
        'DJANGO_SETTINGS_MODULE': 'config.settings.demo', 'ADMINCORE_PRESET': 'demo',
        'ADMINCORE_MODULES': 'files,tasks,notifications,data_io,approvals,system,organization,example',
        'ADMINCORE_ADMIN_USERNAME': 'demo_admin', 'ADMINCORE_ADMIN_EMAIL': 'admin@example.invalid',
        'ADMINCORE_DEMO_INSTANCE': instance, 'ADMINCORE_DEMO_RESET_TOKEN': secrets.token_hex(32),
        'ADMINCORE_DEMO_EDITOR_PASSWORD': secrets.token_urlsafe(40),
        'ADMINCORE_DEMO_VIEWER_PASSWORD': secrets.token_urlsafe(40),
        'ADMINCORE_STORAGE_BACKEND': 'local', 'ADMINCORE_BACKUP_ENABLED': 'False',
        'AUTH_EMAIL_ENABLED': 'False', 'NOTIFICATION_EMAIL_ENABLED': 'False',
        'ADMINCORE_NOTIFICATION_EXTERNAL_CHANNELS_JSON': '{}',
        'ADMINCORE_IMAGE_PROCESSING_ENABLED': 'False', 'AUTH_LOGIN_CAPTCHA_ENABLED': 'False',
    }
    # 此文件由上方create_project新建；绝不读取源仓库的实际.env。
    environment = root / '.env'
    lines = []
    for line in environment.read_text(encoding='utf-8').splitlines():
        key = line.partition('=')[0]
        lines.append(key + '=' + replacements.pop(key) if key in replacements else line)
    lines.extend(key + '=' + value for key, value in replacements.items())
    environment.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    override = root / 'compose.project.yml'
    content = override.read_text(encoding='utf-8')
    for service in ('backend', 'worker', 'beat'):
        content = content.replace('  ' + service + ':\n', '  ' + service + ':\n    environment:\n'
            '      DJANGO_ENV: demo\n      DJANGO_SETTINGS_MODULE: config.settings.demo\n'
            '      DJANGO_DEBUG: "False"\n')
    override.write_text(content, encoding='utf-8', newline='\n')
    demo = {'schema_version': 1, 'demo_instance': instance, 'project_instance': metadata['instance_id'],
            'project_name': name, 'database_name': 'admincore_demo_' + instance}
    (root / DEMO_META).write_text(json.dumps(demo, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (root / 'PROJECT.md').write_text(
        '# AdminCore 独立演示\n\n只绑定本机 HTTP，不得作为生产部署模板。\n\n'
        '启动：`python scripts/project.py up`；停止并保留卷：`python scripts/project.py stop`。\n'
        '访问 http://127.0.0.1:' + str(frontend_port) + ' 。\n'
        '账号：demo_admin、demo_editor、demo_viewer；三个独立随机密码只在本项目私有.env中。\n'
        '对应 ADMINCORE_ADMIN_PASSWORD、ADMINCORE_DEMO_EDITOR_PASSWORD、ADMINCORE_DEMO_VIEWER_PASSWORD。\n'
        '重置前确认不含真实资料：`python scripts/demo_project.py reset --confirm-instance ' + instance + '`。\n'
        '重置清空本实例演示数据库并恢复演示账号/数据，旧会话失效；媒体卷保留，不自动删除上传文件。\n'
        '初始化重复执行不覆盖已有修改。此目录无源项目凭据或Git历史。\n', encoding='utf-8')
    return demo


def reset_demo(root, *, confirm_instance):
    root = Path(root).resolve()
    metadata = load_project(root)
    path = root / DEMO_META
    try:
        if path.is_symlink() or path.stat().st_size > 4096:
            raise ValueError()
        demo = json.loads(path.read_text(encoding='utf-8'))
        instance = demo['demo_instance']
        if (demo['schema_version'] != 1 or len(instance) != 32
                or any(c not in '0123456789abcdef' for c in instance)
                or confirm_instance != instance
                or demo['project_instance'] != metadata['instance_id']
                or demo['project_name'] != metadata['project_name']
                or demo['database_name'] != 'admincore_demo_' + instance
                or metadata['project_name'] != 'admincore-demo-' + instance[:16]):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise ProjectError('演示元数据或实例确认无效，未停止或修改任何服务') from None
    verify_ownership(root)
    base = compose_command(root, 'status')[:-1]
    # 停止写入者后才重置；随机令牌在容器内读取，不进入宿主命令行或输出。
    subprocess.run(base + ['stop', 'frontend', 'worker', 'beat', 'backend'], cwd=root, check=True, timeout=120)
    code = ('import os; os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.demo"); '
            'import django; django.setup(); from django.core.management import call_command; '
            'call_command("demo_admincore", reset=True, confirm=os.environ.get("ADMINCORE_DEMO_RESET_TOKEN", ""))')
    result = subprocess.run(base + ['run', '--rm', '--no-deps', 'backend', 'python', '-c', code],
                            cwd=root, check=False, timeout=180)
    if result.returncode:
        raise ProjectError('重置失败，演示写入服务保持停止；请保留日志核查后手动启动')
    subprocess.run(base + ['up', '-d', '--wait', '--wait-timeout', '180'], cwd=root, check=True, timeout=240)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    create = sub.add_parser('create')
    create.add_argument('target', type=Path)
    create.add_argument('--ref', default='HEAD')
    create.add_argument('--frontend-port', type=int, default=8088)
    create.add_argument('--backend-port', type=int, default=8008)
    create.add_argument('--start', action='store_true')
    reset = sub.add_parser('reset')
    reset.add_argument('--confirm-instance', required=True)
    options = parser.parse_args()
    try:
        if options.action == 'create':
            demo = create_demo(options.target, ref=options.ref, frontend_port=options.frontend_port,
                               backend_port=options.backend_port)
            print(json.dumps({'created': str(options.target.resolve()), **demo,
                              'credentials': '仅写入演示项目私有.env，未输出'}, ensure_ascii=False))
            if options.start:
                run_project(options.target, 'up')
        else:
            reset_demo(Path(__file__).resolve().parents[1], confirm_instance=options.confirm_instance)
    except (ProjectError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, '演示操作未完成：' + str(exc) + '\n')


if __name__ == '__main__':
    main()
