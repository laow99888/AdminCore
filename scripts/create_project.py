"""从明确Git提交导出独立项目；不复制工作区环境、数据或Git历史。"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import secrets
import socket
import subprocess
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
META = 'admincore.project.json'
NAME = re.compile(r'[a-z][a-z0-9-]{1,31}')
REVISION = re.compile(r'[0-9a-f]{40}')
MAX_BYTES = 100 * 1024 * 1024
MAX_FILES = 10000
REQUIRED = ('.env.example', '.gitignore', 'docker-compose.yml', 'compose.minimal.yml',
            'backend/config/base-version.json', 'backend/requirements.lock',
            'frontend/package-lock.json', 'scripts/create_project.py', 'scripts/project.py')


class ProjectError(ValueError):
    pass


def safe_source_path(name):
    path = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or path.is_absolute()
            or any(part in ('', '.', '..') for part in name.split('/'))):
        raise ProjectError('模板包含不安全路径')
    return path


def allowed_file(name):
    path = safe_source_path(name)
    denied = {'.git', '.codex-validation', 'node_modules', 'venv', '.venv', '__pycache__',
              '.pytest_cache', 'backups', 'test-results', 'playwright-report', 'coverage', 'dist'}
    if any(part in denied for part in path.parts):
        return False
    if name.startswith(('backend/media/', 'backend/logs/', 'backend/staticfiles/')):
        return False
    if any(part.startswith('.env') and part not in ('.env.example', '.env.modules.example') for part in path.parts):
        return False
    return path.suffix.lower() not in {'.pem', '.key', '.p12', '.pfx', '.dump', '.sqlite3', '.pyc', '.log'}


def snapshot(source, ref='HEAD'):
    source = Path(source).resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/_.-]{0,199}', ref):
        raise ProjectError('提交引用格式无效')
    def git(*args):
        try:
            return subprocess.run(['git', '-C', str(source), *args], check=True, capture_output=True,
                                  timeout=60).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProjectError('无法读取指定Git提交；请确认源仓库和引用') from exc
    revision = git('rev-parse', '--verify', ref + '^{commit}').decode('ascii').strip()
    if not REVISION.fullmatch(revision):
        raise ProjectError('无法确定源提交')
    archive = git('archive', '--format=tar', revision)
    if len(archive) > MAX_BYTES:
        raise ProjectError('模板归档超过100MiB限制')
    files, total = {}, 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as tar:
        for entry in tar:
            name = entry.name.rstrip('/')
            safe_source_path(name)
            if entry.isdir():
                continue
            if not entry.isfile():
                raise ProjectError('模板不允许符号链接、硬链接或设备文件')
            if not allowed_file(name) or name in (META, 'compose.project.yml', 'PROJECT.md'):
                continue
            total += entry.size
            if total > MAX_BYTES or len(files) >= MAX_FILES or name in files:
                raise ProjectError('模板文件大小、数量或重复路径无效')
            files[name] = (tar.extractfile(entry).read(), entry.mode)
    if not all(name in files for name in REQUIRED):
        raise ProjectError('源提交缺少完整模板文件；请选包含初始化工具的底座提交')
    version = json.loads(files['backend/config/base-version.json'][0].decode('utf-8'))['version']
    if not isinstance(version, str) or not re.fullmatch(r'[0-9A-Za-z.+-]{1,100}', version):
        raise ProjectError('底座版本无效')
    return revision, version, files


def manifest(files):
    return {name: hashlib.sha256(value[0]).hexdigest() for name, value in sorted(files.items())}


def check_ports(frontend_port, backend_port):
    if (type(frontend_port) is not int or type(backend_port) is not int
            or not all(1 <= value <= 65535 for value in (frontend_port, backend_port))
            or frontend_port == backend_port):
        raise ProjectError('前后端端口必须为不同的1–65535整数')
    for port in (frontend_port, backend_port):
        try:
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', port))
        except OSError as exc:
            raise ProjectError('端口已占用：' + str(port)) from exc


def create_project(target, *, name, preset='minimal', source=ROOT, ref='HEAD',
                   frontend_port=8080, backend_port=8001):
    if not NAME.fullmatch(name) or preset not in ('minimal', 'standard'):
        raise ProjectError('项目名使用2–32位小写字母/数字/连字符，预设仅minimal/standard')
    source, target = Path(source).resolve(), Path(target).resolve()
    if target.exists() or target.is_relative_to(source) or source.is_relative_to(target):
        raise ProjectError('目标必须是源仓库之外的新目录；不覆盖或合并已有目录')
    check_ports(frontend_port, backend_port)
    revision, version, files = snapshot(source, ref)
    target.mkdir(mode=0o700, parents=True, exist_ok=False)
    # 新目录创建后发生错误也保留，便于核查，不猜测删除用户随后加入的内容。
    for path, (content, mode) in files.items():
        output = target.joinpath(*PurePosixPath(path).parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as stream:
            stream.write(content)
        output.chmod(mode & 0o777)
    values = {
        'DJANGO_SECRET_KEY': secrets.token_urlsafe(64), 'DB_PASSWORD': secrets.token_urlsafe(40),
        'ADMINCORE_ADMIN_PASSWORD': secrets.token_urlsafe(40), 'ADMINCORE_ADMIN_USERNAME': 'admin',
        'ADMINCORE_ADMIN_EMAIL': '', 'DB_NAME': name.replace('-', '_'), 'DJANGO_ENV': 'production',
        'DJANGO_DEBUG': 'False', 'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend',
        'COMPOSE_PROJECT_NAME': name, 'ADMINCORE_PRESET': preset,
        'FRONTEND_PORT': str(frontend_port), 'BACKEND_PORT': str(backend_port),
        'BACKEND_BIND_ADDRESS': '127.0.0.1', 'USE_TLS': 'False', 'SECURE_HSTS_SECONDS': '0',
        'AUTH_EMAIL_ENABLED': 'False', 'NOTIFICATION_EMAIL_ENABLED': 'False',
        'ADMINCORE_BACKUP_ENABLED': 'False', 'ADMINCORE_IMAGE_PROCESSING_ENABLED': 'False',
        'ALLOW_PUBLIC_REGISTRATION': 'False',
    }
    lines = []
    for line in files['.env.example'][0].decode('utf-8-sig').splitlines():
        key = line.split('=', 1)[0]
        lines.append(key + '=' + values.pop(key) if key in values else line)
    lines.extend(key + '=' + value for key, value in values.items())
    environment = target / '.env'
    with environment.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('\n'.join(lines) + '\n')
    environment.chmod(0o600)  # Windows ACL由所在私有目录继承，不声称chmod等同ACL。
    metadata = {'schema_version': 1, 'project_name': name, 'preset': preset,
                'instance_id': uuid.uuid4().hex, 'source_revision': revision,
                'base_version': version, 'files': manifest(files)}
    (target / META).write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    label = 'io.admincore.instance: "' + metadata['instance_id'] + '"'
    override = 'services:\n'
    for service in ('db', 'redis', 'backend', 'worker', 'beat', 'frontend'):
        override += '  ' + service + ':\n    labels:\n      ' + label + '\n'
        if service == 'frontend':
            override += '    ports: !override\n      - "127.0.0.1:${FRONTEND_PORT}:80"\n'
    override += 'volumes:\n'
    for volume in ('pgdata', 'redisdata', 'media', 'staticfiles', 'logs'):
        override += '  ' + volume + ':\n    labels:\n      ' + label + '\n'
    override += 'networks:\n  default:\n    labels:\n      ' + label + '\n'
    (target / 'compose.project.yml').write_text(override, encoding='utf-8')
    (target / 'PROJECT.md').write_text(
        '# ' + name + '\n\n底座 ' + version + '，源提交 `' + revision + '`。\n\n'
        '运行 `python scripts/project.py up` 构建启动，`status` 查看，`check` 检查，`stop` 停止（保留卷）。\n'
        '首次管理员admin的随机密码仅保存在本目录 `.env`，首次登录必须改密；不要提交该文件。\n'
        '访问 http://127.0.0.1:' + str(frontend_port) + ' 。当前只绑定本机HTTP，公网TLS须按部署手册独立配置。\n'
        '本项目没有复制Git历史；可自行git init提交源码和admincore.project.json，环境与数据不入Git。\n'
        '升级前阅读 docs/底座版本与项目升级.md；upgrade-plan只比较摘要，绝不自动覆盖、迁移或删除。\n', encoding='utf-8')
    return metadata


def load_project(root):
    root = Path(root).resolve()
    try:
        metadata_path = root / META
        if metadata_path.is_symlink() or metadata_path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('元数据路径或大小无效')
        data = json.loads(metadata_path.read_text(encoding='utf-8'))
        if not (type(data['schema_version']) is int and data['schema_version'] == 1
                and NAME.fullmatch(data['project_name'])
                and data['preset'] in ('minimal', 'standard') and REVISION.fullmatch(data['source_revision'])
                and re.fullmatch(r'[0-9a-f]{32}', data['instance_id'])
                and isinstance(data['base_version'], str)
                and re.fullmatch(r'[0-9A-Za-z.+-]{1,100}', data['base_version'])
                and isinstance(data['files'], dict) and len(data['files']) <= MAX_FILES):
            raise ValueError('元数据字段无效')
        for path, digest in data['files'].items():
            if not allowed_file(path) or not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError('摘要清单无效')
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ProjectError('项目元数据缺失或无效；拒绝猜测Compose项目或源版本') from exc
    return data


def compose_command(root, action):
    root = Path(root).resolve()
    data = load_project(root)
    if action not in ('up', 'status', 'stop', 'check'):
        raise ProjectError('未登记项目命令')
    files = ['docker-compose.yml'] + (['compose.minimal.yml'] if data['preset'] == 'minimal' else []) + ['compose.project.yml']
    paths = [root / file for file in ['.env', *files]]
    if any(not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root) for path in paths):
        raise ProjectError('项目配置缺失，未启动任何服务')
    command = ['docker', 'compose', '-p', data['project_name'], '--env-file', str(root / '.env')]
    for file in files:
        command.extend(['-f', str(root / file)])
    arguments = {'up': ['up', '-d', '--build', '--wait', '--wait-timeout', '180'],
                 'status': ['ps'], 'stop': ['stop'],
                 'check': ['exec', '-T', 'backend', 'python', 'manage.py', 'migrate', '--check']}[action]
    if action == 'up' and data['preset'] == 'minimal':
        arguments += ['db', 'backend', 'frontend']
    return command + arguments


def verify_ownership(root):
    """Refuse collisions with any foreign container, volume or network."""
    data = load_project(root)
    def docker(*arguments):
        try:
            result = subprocess.run(['docker', *arguments], capture_output=True, text=True,
                                    encoding='utf-8', check=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProjectError('无法确认Docker项目归属；未执行项目命令') from exc
        return result.stdout
    selector = 'label=com.docker.compose.project=' + data['project_name']
    for list_args, inspect_args, label_field in (
        (['ps', '-aq'], ['inspect'], '.Config.Labels'),
        (['volume', 'ls', '-q'], ['volume', 'inspect'], '.Labels'),
        (['network', 'ls', '-q'], ['network', 'inspect'], '.Labels'),
    ):
        ids = docker(*list_args, '--filter', selector).split()
        for identifier in ids:
            labels = json.loads(docker(*inspect_args, '--format', '{{json ' + label_field + '}}', identifier)) or {}
            if labels.get('io.admincore.instance') != data['instance_id']:
                raise ProjectError('同名Compose项目存在其他归属资源；拒绝接管、停止或修改')


def run_project(root, action):
    root = Path(root).resolve()
    command = compose_command(root, action)
    verify_ownership(root)
    if action in ('status', 'stop', 'check'):
        return subprocess.run(command, cwd=root, check=False).returncode
    folder = root / '.codex-validation'
    folder.mkdir(exist_ok=True)
    logfile = folder / 'project-start.log'
    with logfile.open('a', encoding='utf-8') as output:
        result = subprocess.run(command, cwd=root, stdout=output, stderr=subprocess.STDOUT, timeout=1200)
    if result.returncode:
        raise ProjectError('启动失败，项目/卷及日志保留：' + str(logfile))
    return 0


def upgrade_plan(root, source, ref='HEAD'):
    root = Path(root).resolve()
    baseline = load_project(root)
    revision, version, files = snapshot(source, ref)
    proposed = manifest(files)
    changes = []
    for path in sorted(set(baseline['files']) | set(proposed)):
        before, after = baseline['files'].get(path), proposed.get(path)
        local = root.joinpath(*PurePosixPath(path).parts)
        unsafe = local.is_symlink() or not local.resolve().is_relative_to(root)
        if unsafe or (local.exists() and not local.is_file()):
            current = 'unsafe_path'
        else:
            current = hashlib.sha256(local.read_bytes()).hexdigest() if local.is_file() else None
        if before != after or before != current:
            changes.append({'path': path, 'upstream_changed': before != after, 'local_changed': before != current,
                'action': 'delete' if after is None else 'add' if before is None else 'modify',
                'conflict': unsafe or (before != after and before != current and current != after)})
    return {'schema_version': 1, 'from_revision': baseline['source_revision'], 'to_revision': revision,
            'from_version': baseline['base_version'], 'to_version': version, 'changes': changes,
            'conflicts': sum(row['conflict'] for row in changes), 'read_only': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    parser.add_argument('--name', required=True)
    parser.add_argument('--preset', choices=['minimal', 'standard'], default='minimal')
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--frontend-port', type=int, default=8080)
    parser.add_argument('--backend-port', type=int, default=8001)
    parser.add_argument('--start', action='store_true')
    options = parser.parse_args()
    try:
        data = create_project(options.target, name=options.name, preset=options.preset, ref=options.ref,
                              frontend_port=options.frontend_port, backend_port=options.backend_port)
        print(json.dumps({'created': str(options.target.resolve()), 'project': data['project_name'],
                          'base_version': data['base_version'], 'source_revision': data['source_revision'],
                          'credentials': '仅保存在新项目.env，未输出密码'}, ensure_ascii=False))
        if options.start:
            run_project(options.target, 'up')
            print('项目已启动；停止命令：python scripts/project.py stop（在新项目目录执行）')
    except (ProjectError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, '初始化未完成：' + str(exc) + '\n')


if __name__ == '__main__':
    main()
