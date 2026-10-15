"""从真实提交导出精简/标准项目，验收空库、密码、保留及归属隔离。"""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import uuid

import requests

from create_project import (ROOT, META, ProjectError, create_project, compose_command,
                            run_project, upgrade_plan, verify_ownership)


def main():
    identifier = uuid.uuid4().hex[:8]
    folder = ROOT / '.codex-validation' / ('admincore-project-template-' + identifier)
    folder.mkdir(parents=True)
    temporary = Path(tempfile.mkdtemp(prefix='admincore-template-' + identifier + '-')).resolve()
    checks, projects = [], []
    report = {'passed': False, 'project_prefix': 'ac-template-' + identifier}

    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label)
        print('通过：' + label, flush=True)

    def command(root, action):
        with (folder / 'docker.log').open('a', encoding='utf-8') as output:
            result = subprocess.run(compose_command(root, 'status')[:-1] + action, cwd=root,
                stdout=output, stderr=subprocess.STDOUT, timeout=360)
        if result.returncode:
            raise RuntimeError('隔离Compose命令失败，见docker.log')

    def api(base, path, *, token=None, method='GET', data=None, expected=200, language=None):
        response = requests.request(method, base + path, json=data,
            headers={**({'Authorization': 'Bearer ' + token} if token else {}),
                     **({'Accept-Language': language} if language else {})}, timeout=20)
        check(path + ' → ' + str(expected), response.status_code == expected)
        if language:
            check('语言响应及缓存变体 ' + language, response.headers.get('Content-Language') == ('en' if language == 'en-US' else 'zh-hans')
                  and 'Accept-Language' in response.headers.get('Vary', ''))
        return response.json()

    try:
        for index, preset in enumerate(('minimal', 'standard')):
            target = temporary / preset
            name = report['project_prefix'] + '-' + preset
            port = 18500 + index * 2
            data = create_project(target, name=name, preset=preset,
                                  frontend_port=port, backend_port=port + 1)
            projects.append(target)
            check(preset + '源码无原环境/历史/业务文件', not (target / '.git').exists()
                and not (target / '.env.admin-access.txt').exists()
                and not (target / 'backend/media').exists())
            check(preset + '初始三方差异为空', upgrade_plan(target, ROOT)['changes'] == [])
            check(preset + '实际构建并启动', run_project(target, 'up') == 0)
            result = subprocess.run(compose_command(target, 'status') + ['--status', 'running', '--services'],
                                    cwd=target, capture_output=True, text=True, check=True)
            expected_services = {'db', 'backend', 'frontend'}
            if preset == 'standard': expected_services |= {'redis', 'worker', 'beat'}
            check(preset + '服务数量符合预设', set(result.stdout.split()) == expected_services)
            env = dict(line.split('=', 1) for line in (target / '.env').read_text(encoding='utf-8').splitlines()
                       if '=' in line and not line.startswith('#'))
            password = env['ADMINCORE_ADMIN_PASSWORD']
            base = 'http://127.0.0.1:' + str(port) + '/api/v1/'
            api(base, 'health/')
            api(base, 'health/live/')
            token = api(base, 'auth/login/', method='POST', data={'username': 'admin', 'password': password})['access']
            import secrets
            new_password = secrets.token_urlsafe(40)
            api(base, 'auth/change_password/', token=token, method='POST', data={
                'old_password': password, 'new_password': new_password, 'new_password2': new_password})
            token = api(base, 'auth/login/', method='POST', data={'username': 'admin', 'password': new_password})['access']
            for language, message in [('en-US', 'The two passwords do not match.'), ('zh-CN', '两次输入的密码不一致')]:
                errors = api(base, 'auth/change_password/', token=token, method='POST', expected=400, language=language,
                    data={'old_password': new_password, 'new_password': secrets.token_urlsafe(40), 'new_password2': 'mismatch'})
                check(preset + '真实错误语言 ' + language, errors['data']['new_password'] == message)
            capabilities = api(base, 'modules/', token=token)['data']
            check(preset + '契约及预设', capabilities['contract_version'] == 1 and capabilities['preset'] == preset)
            if preset == 'standard':
                check('版本信息与导出一致', api(base, 'system/information/', token=token)['data']['base_version'] == data['base_version'])
            else:
                api(base, 'system/information/', token=token, expected=404)
            check(preset + '迁移检查', run_project(target, 'check') == 0)
            # 同名但不同实例必须拒绝停止正在运行的项目。
            duplicate = temporary / (preset + '-duplicate')
            create_project(duplicate, name=name, preset=preset, frontend_port=port + 10, backend_port=port + 11)
            refused = False
            try:
                run_project(duplicate, 'stop')
            except ProjectError:
                refused = True
            check(preset + '真实重名实例不能停止已有服务', refused)
            api(base, 'health/')
            check(preset + '停止保留数据', run_project(target, 'stop') == 0)
            check(preset + '恢复已存在项目', run_project(target, 'up') == 0)
            api(base, 'auth/login/', method='POST', data={'username': 'admin', 'password': new_password})
            api(base, 'auth/login/', method='POST', data={'username': 'admin', 'password': password}, expected=401)
            check(preset + '保留元数据不含密码', password not in (target / META).read_text(encoding='utf-8'))
            verify_ownership(target)
            command(target, ['down', '-v', '--remove-orphans'])  # 仅随机测试项目，非用户运维入口。
            projects.remove(target)
            shutil.copyfile(target / '.codex-validation/project-start.log', folder / (preset + '-start.log'))
        report['passed'] = True
    finally:
        report['checks'] = checks
        if report['passed']:
            if temporary.parent != Path(tempfile.gettempdir()).resolve() or not temporary.name.startswith('admincore-template-' + identifier + '-'):
                raise RuntimeError('拒绝清理意外路径')
            shutil.rmtree(temporary)
            report['cleaned'] = ['两个隔离Compose项目/卷/网络', str(temporary)]
            report['released_ports'] = [18500, 18501, 18502, 18503]
        else:
            report['retained_fixture'] = str(temporary)
            for target in projects:
                try:
                    verify_ownership(target)
                    command(target, ['stop'])
                    if (target / '.codex-validation/project-start.log').is_file():
                        shutil.copyfile(target / '.codex-validation/project-start.log', folder / (target.name + '-start.log'))
                except (ProjectError, OSError, subprocess.SubprocessError, RuntimeError):
                    pass
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'evidence': str(folder), **report}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
