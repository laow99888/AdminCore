"""用无网络、无端口的合成服务验证镜像固定与停止恢复；不接触业务数据。"""
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from prepare_release import prepare, verify

ROOT = Path(__file__).resolve().parents[1]


def main():
    project = 'admincore-release-' + uuid.uuid4().hex[:8]
    folder = ROOT / '.codex-validation' / project
    folder.mkdir(parents=True)
    workspace = folder / 'workspace'
    workspace.mkdir()
    base_image = 'python:' + (ROOT / '.python-version').read_text().strip() + '-slim'
    checks = []
    report = {'passed': False, 'project': project, 'ports': []}
    base = ['docker', 'compose', '-p', project, '--project-directory', str(workspace),
            '--env-file', str(workspace / '.env'), '-f', str(workspace / 'compose.yml')]

    def run(arguments):
        with (folder / 'docker.log').open('a', encoding='utf-8') as log:
            subprocess.run(arguments, cwd=workspace, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=180)

    def check(label):
        checks.append(label)
        print('通过：' + label, flush=True)

    try:
        for name in ('backend', 'frontend'):
            context = workspace / name
            context.mkdir()
            (context / 'Dockerfile').write_text(
                'FROM ' + base_image + '\nLABEL io.admincore.release-fixture="' + name + '"\n'
                'CMD ["python", "-c", "import time; time.sleep(600)"]\n', encoding='utf-8')
        services = {}
        for name in ('backend', 'worker', 'beat', 'realtime', 'frontend'):
            services[name] = {'build': {'context': './frontend' if name == 'frontend' else './backend'},
                              'network_mode': 'none',
                              'healthcheck': {'test': ['CMD', 'python', '-c', 'pass'],
                                              'interval': '1s', 'timeout': '2s', 'retries': 5}}
        (workspace / 'compose.yml').write_text(json.dumps({'services': services}), encoding='utf-8')
        (workspace / '.env').write_text('PRIVATE_FIXTURE_VALUE=must-not-export\n', encoding='utf-8')
        release = folder / 'release'
        manifest = prepare(workspace, ['compose.yml'], release, project=project)
        assert len({manifest['images'][name] for name in ('backend', 'worker', 'beat', 'realtime')}) == 1
        check('四个Python角色绑定同一内容ID')
        assert all('must-not-export' not in file.read_text(encoding='utf-8') for file in release.iterdir())
        check('发布文件不含环境值')
        # 将可变构建标签改指另一个镜像，覆盖文件仍必须使用原内容ID。
        # BuildKit 的基础镜像缓存不保证存在同名本地标签；使用本次已加载的前端镜像。
        assert manifest['images']['frontend'] != manifest['images']['backend']
        run(['docker', 'tag', manifest['images']['frontend'], project + '-backend:latest'])
        pinned = base + ['-f', str(release / 'compose.release.yml')]
        run(pinned + ['up', '-d', '--no-build', '--wait', '--wait-timeout', '30'])
        verify(workspace, ['compose.yml'], release, project=project)
        check('可变标签改指后五个实例仍使用发布ID且健康')
        run(pinned + ['stop'])
        run(pinned + ['up', '-d', '--no-build', '--wait', '--wait-timeout', '30'])
        verify(workspace, ['compose.yml'], release, project=project)
        check('停止恢复后镜像和角色集合保持一致')
        report['passed'] = True
    finally:
        report['checks'] = checks
        if (workspace / 'compose.yml').exists():
            try:
                run(base + ['down'])
                run(['docker', 'image', 'rm', project + '-backend:latest', project + '-frontend:latest'])
            except subprocess.SubprocessError:
                report['cleanup_failed'] = True
        if report['passed'] and not report.get('cleanup_failed'):
            if workspace.parent.resolve() != folder.resolve() or workspace.is_symlink():
                raise RuntimeError('工作副本清理边界无效')
            report['cleaned'] = ['五个隔离容器及本次构建标签']
            for attempt in range(3):
                try:
                    shutil.rmtree(workspace)
                    report['cleaned'].append(str(workspace))
                    break
                except PermissionError:
                    if attempt == 2:
                        report['retained_fixture'] = str(workspace)
                    else:
                        time.sleep(0.5)
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'evidence': str(folder), **report}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
