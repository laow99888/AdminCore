"""准备本机不可变发布覆盖文件；不启动服务，不导出解析后的环境。"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

ROLES = ('backend', 'worker', 'beat', 'realtime')
IMAGE_ID = re.compile(r'sha256:[0-9a-f]{64}')
SERVICE = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*')


class ReleaseError(ValueError):
    pass


def command(arguments, root, *, capture=True, timeout=120):
    result = subprocess.run(arguments, cwd=root, capture_output=capture, text=True,
                            encoding='utf-8', errors='replace', timeout=timeout)
    if result.returncode:
        # config / inspect 的完整输出可能包含环境配置，不在异常中复制。
        raise ReleaseError('发布命令失败；未生成或修改发布文件')
    return result.stdout if capture else None


def prefix(root, files, env_file, project=None):
    arguments = ['docker', 'compose', '--project-directory', str(root)]
    if project:
        if not SERVICE.fullmatch(project):
            raise ReleaseError('项目名无效')
        arguments += ['-p', project]
    for file in files:
        path = (root / file).resolve()
        if not path.is_file():
            raise ReleaseError('编排文件不存在')
        arguments += ['-f', str(path)]
    if env_file:
        path = (root / env_file).resolve()
        if not path.is_file():
            raise ReleaseError('环境文件不存在')
        arguments += ['--env-file', str(path)]
    return arguments


def build_targets(config):
    services = config.get('services', {})
    if not all(name in services and services[name].get('build') for name in ('backend', 'frontend')):
        raise ReleaseError('发布需要 backend 和 frontend 构建定义')
    backend = services['backend']['build']
    for name, service in services.items():
        if not SERVICE.fullmatch(name):
            raise ReleaseError('服务名无效')
        if name in ROLES:
            if service.get('build') != backend:
                raise ReleaseError('Python角色构建定义不一致，拒绝共用镜像：' + name)
        elif service.get('build') and name != 'frontend':
            raise ReleaseError('存在未登记构建服务：' + name)
    return ['backend', 'frontend']


def pinned_overlay(images):
    lines = ['# 本机不可变镜像ID；部署时叠加原编排并使用 up -d --no-build。', 'services:']
    for name, image in sorted(images.items()):
        if not SERVICE.fullmatch(name) or not IMAGE_ID.fullmatch(image):
            raise ReleaseError('发布服务名或镜像ID无效')
        lines += ['  ' + name + ':', '    image: ' + json.dumps(image),
                  '    build: !reset null', '    pull_policy: never']
    return '\n'.join(lines) + '\n'


def prepare(root, files, output, *, env_file='.env', project=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise ReleaseError('发布目录已存在；拒绝覆盖旧构件')
    base = prefix(root, files, env_file, project)
    config = json.loads(command(base + ['config', '--format', 'json'], root))
    targets = build_targets(config)
    # 只构建一次后端；worker/beat/realtime 从同一个内容ID启动。
    command(base + ['build', *targets], root, capture=False, timeout=1200)
    images = {}
    for name, service in config['services'].items():
        target = 'backend' if name in ROLES else name
        original = config['services'][target]
        reference = original.get('image') or config['name'] + '-' + target
        # 不自动拉取/变更第三方镜像；缺失时先显式 pull，再重新准备。
        image = command(['docker', 'image', 'inspect', reference, '--format', '{{.Id}}'], root).strip()
        if not IMAGE_ID.fullmatch(image):
            raise ReleaseError('无法确定本机镜像ID：' + name)
        images[name] = image
    overlay = pinned_overlay(images)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'compose.release.yml').write_text(overlay, encoding='utf-8', newline='\n')
    manifest = {'schema_version': 1, 'project': config['name'],
                'created_at': datetime.now(timezone.utc).isoformat(), 'images': images}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def verify(root, files, output, *, env_file='.env', project=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    images = manifest['images']
    # 验证清单本身的允许值，避免篡改的清单变成任意 Docker 参数。
    expected_overlay = pinned_overlay(images)
    if manifest.get('schema_version') != 1 or (output / 'compose.release.yml').read_text(encoding='utf-8') != expected_overlay:
        raise ReleaseError('发布清单与覆盖文件不一致')
    base = prefix(root, [*files, str(output / 'compose.release.yml')], env_file, project)
    config = json.loads(command(base + ['config', '--format', 'json'], root))
    if config['name'] != manifest['project'] or set(config['services']) != set(images):
        raise ReleaseError('发布项目或启用服务集合不一致')
    for name, image in images.items():
        service = config['services'][name]
        if service.get('image') != image or service.get('build') or service.get('pull_policy') != 'never':
            raise ReleaseError('发布仍允许重建或更换镜像：' + name)
        containers = command(base + ['ps', '--all', '--quiet', name], root).split()
        if not containers:
            raise ReleaseError('发布服务没有运行实例：' + name)
        for container in containers:
            details = json.loads(command(['docker', 'inspect', container], root))[0]
            state = details['State']
            if details['Image'] != image or not state.get('Running') or state.get('Health', {}).get('Status', 'healthy') != 'healthy':
                raise ReleaseError('发布实例镜像、运行或健康状态不匹配：' + name)
    return {'passed': True, 'project': manifest['project'], 'services': sorted(images)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('-f', '--file', action='append', dest='files')
    parser.add_argument('--env-file', default='.env')
    parser.add_argument('-p', '--project-name')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    try:
        operation = verify if args.verify else prepare
        result = operation(args.root, args.files or ['docker-compose.yml'], args.output,
                           env_file=args.env_file, project=args.project_name)
        print(json.dumps(result, ensure_ascii=False))
    except (ReleaseError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, '发布准备/复核失败：' + str(error) + '\n')


if __name__ == '__main__':
    main()
