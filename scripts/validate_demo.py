"""只验收新建一次性演示项目；成功清理本项目，失败停写并保留证据。"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

import requests

from create_project import ROOT, compose_command, run_project, verify_ownership
from demo_project import create_demo, reset_demo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--frontend-port', type=int, default=18520)
    parser.add_argument('--backend-port', type=int, default=18521)
    options = parser.parse_args()
    identifier = uuid.uuid4().hex[:8]
    folder = ROOT / '.codex-validation' / ('admincore-demo-' + identifier)
    folder.mkdir(parents=True)
    temporary = Path(tempfile.mkdtemp(prefix='admincore-demo-' + identifier + '-')).resolve()
    target = temporary / 'project'
    checks = []
    report = {'passed': False}
    created = False

    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label)
        print('通过：' + label, flush=True)

    def command(arguments, *, expected=0, fragment=''):
        result = subprocess.run(compose_command(target, 'status')[:-1] + arguments,
            cwd=target, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=420,
            text=True, encoding='utf-8', errors='replace')
        with (folder / 'docker.log').open('a', encoding='utf-8') as output:
            output.write(result.stdout)
        check('隔离命令成功' if expected == 0 else '非法演示操作立即拒绝',
              (result.returncode == 0 if expected == 0 else result.returncode != 0)
              and fragment in result.stdout)

    def api(path, *, token=None, data=None, expected=200, method='GET'):
        response = requests.request(method, 'http://127.0.0.1:' + str(options.frontend_port)
            + '/api/v1/' + path, json=data,
            headers={'Authorization': 'Bearer ' + token} if token else {}, timeout=20)
        check(path + ' 返回 ' + str(expected), response.status_code == expected)
        return response.json()

    try:
        data = create_demo(target, ref=options.ref, frontend_port=options.frontend_port,
                           backend_port=options.backend_port)
        created = True
        report.update({'project': data['project_name'], 'instance': data['demo_instance']})
        check('导出不含源环境和旧媒体', not (target / '.env.admin-access.txt').exists()
              and not (target / 'backend/media').exists() and not (target / '.git').exists())
        check('构建启动独立演示项目', run_project(target, 'up') == 0)
        environment = dict(line.split('=', 1) for line in (target / '.env').read_text(encoding='utf-8').splitlines()
                           if '=' in line and not line.startswith('#'))
        api('health/')
        tokens = {}
        for username, key in (('demo_admin', 'ADMINCORE_ADMIN_PASSWORD'),
                              ('demo_editor', 'ADMINCORE_DEMO_EDITOR_PASSWORD'),
                              ('demo_viewer', 'ADMINCORE_DEMO_VIEWER_PASSWORD')):
            login = api('auth/login/', method='POST', data={'username': username, 'password': environment[key]})
            check(username + ' 不要求改演示初始密码', not login['user']['must_change_password'])
            tokens[username] = login['access']
        api('auth/login/', method='POST', data={'username': 'admin', 'password': 'Admin#12345'}, expected=401)
        api('auth/login/', method='POST', data={'username': 'demo', 'password': 'Demo#12345'}, expected=401)
        for username in ('demo_editor', 'demo_viewer'):
            rows = api('example/items/', token=tokens[username])['data']
            check(username + ' 仅见本人两条工单', rows['pagination']['total'] == 2
                  and all(row['title'].startswith(username) for row in rows['items']))
            api('users/', token=tokens[username], method='POST', data={'username': 'forbidden'}, expected=403)
        rows = api('example/items/', token=tokens['demo_admin'])['data']
        check('演示管理员可见完整六条工单', rows['pagination']['total'] == 6)
        templates = api('notifications/templates/', token=tokens['demo_admin'])['data']['items']
        template = next(row for row in templates if row['code'] == 'demo-welcome')
        preview = api('notifications/templates/' + template['id'] + '/preview/',
            token=tokens['demo_admin'], method='POST', data={'revision': 1, 'values': {'name': '演示访客'}})
        check('演示模板实际替换变量', preview['data']['subject'] == '欢迎 演示访客')
        files = api('files/', token=tokens['demo_admin'])['data']['items']
        image = next(row for row in files if row['original_name'] == '演示图片.png')
        image_preview = requests.get('http://127.0.0.1:' + str(options.frontend_port)
            + '/api/v1/files/' + image['id'] + '/preview/',
            headers={'Authorization': 'Bearer ' + tokens['demo_admin']}, timeout=20)
        check('演示图片通过真实鉴权预览', image_preview.status_code == 200
              and image_preview.headers.get('Content-Type') == 'image/png'
              and image_preview.content.startswith(b'\x89PNG\r\n\x1a\n'))
        item = rows['items'][0]
        api('example/items/' + item['id'] + '/', method='PATCH', token=tokens['demo_admin'],
            data={'title': '保留后续演示修改', 'version': item['version']})
        command(['exec', '-T', 'backend', 'python', 'manage.py', 'bootstrap_admincore'])
        check('重复初始化保留用户修改',
              api('example/items/' + item['id'] + '/', token=tokens['demo_admin'])['data']['title'] == '保留后续演示修改')
        # 错误确认的管理命令在独立真实PG上拒绝，随后原会话仍能读。
        command(['exec', '-T', 'backend', 'python', 'manage.py', 'demo_admincore', '--reset', '--confirm', 'wrong'],
                expected=1, fragment='演示重置确认令牌不匹配')
        api('example/items/', token=tokens['demo_admin'])
        check('宿主脚本安全重置', reset_demo(target, confirm_instance=data['demo_instance']) == 0)
        api('example/items/', token=tokens['demo_admin'], expected=401)
        login = api('auth/login/', method='POST', data={'username': 'demo_admin',
                                                      'password': environment['ADMINCORE_ADMIN_PASSWORD']})
        rows = api('example/items/', token=login['access'])['data']
        check('重置恢复场景且不保留后续数据库修改', rows['pagination']['total'] == 6
              and all(row['title'] != '保留后续演示修改' for row in rows['items']))
        command(['run', '--rm', '--no-deps', '-e', 'DJANGO_ENV=production',
                 '-e', 'DJANGO_SETTINGS_MODULE=config.settings.production', 'backend',
                 'python', 'manage.py', 'check'], expected=1, fragment='生产环境禁止 demo 预设')
        api('health/')
        verify_ownership(target)
        command(['down', '-v', '--remove-orphans'])
        shutil.copyfile(target / '.codex-validation/project-start.log', folder / 'project-start.log')
        report['passed'] = True
    finally:
        report['checks'] = checks
        if report['passed']:
            if (temporary.parent != Path(tempfile.gettempdir()).resolve()
                    or not temporary.name.startswith('admincore-demo-' + identifier + '-')):
                raise RuntimeError('拒绝清理意外临时目录')
            shutil.rmtree(temporary)
            report['cleaned'] = ['本次演示容器/卷/网络', str(temporary)]
            report['released_ports'] = [options.frontend_port, options.backend_port]
        else:
            report['retained_fixture'] = str(temporary)
            if created:
                try:
                    verify_ownership(target)
                    command(['stop'])
                    if (target / '.codex-validation/project-start.log').is_file():
                        shutil.copyfile(target / '.codex-validation/project-start.log', folder / 'project-start.log')
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                    pass
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'evidence': str(folder), **report}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
