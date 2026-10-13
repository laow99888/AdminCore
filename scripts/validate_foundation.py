"""独立 Docker/PostgreSQL 验收；只移除本脚本创建的项目、卷及临时凭据。

用法：backend/venv/Scripts/python.exe scripts/validate_foundation.py
需要 Docker Compose（支持 !override）、本机 18420/18421 空闲以及 requests。
失败保留隔离项目和日志；成功保留报告，关闭容器并移除本次测试卷。
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import secrets
import socket
import subprocess
import sys
import time
import uuid

import requests

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'admincore-foundation-' + uuid.uuid4().hex[:8]
FOLDER = ROOT / '.codex-validation' / PROJECT
BASE = 'http://127.0.0.1:18421/api/v1/'
CHECKS = []


def run(args, *, allowed_failure=False):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    with (FOLDER / 'docker.log').open('a', encoding='utf-8') as log:
        log.write(result.stdout + result.stderr)
    if result.returncode and not allowed_failure:
        raise RuntimeError(f'命令失败，详见 {FOLDER / "docker.log"}')
    return result


def compose(mode, *args):
    files = ['docker-compose.yml', 'compose.minimal.yml', str(FOLDER / 'override.yml')]
    if mode == 'standard':
        files.append(str(FOLDER / 'standard.yml'))
    command = ['docker', 'compose', '-p', PROJECT, '--env-file', str(FOLDER / 'fixture.env')]
    for file in files:
        command += ['-f', file]
    return run(command + list(args))


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)
    print('通过：' + label, flush=True)


def api(path, method='GET', data=None, expected=200, token=None, headers=None):
    request_headers = {'Authorization': 'Bearer ' + token} if token else {}
    request_headers.update(headers or {})
    response = requests.request(method, BASE + path, json=data,
                                headers=request_headers, timeout=40)
    if expected is not None:
        check(method + ' ' + path + ' → ' + str(expected), response.status_code == expected)
    return response


def concurrent_patch(path, payloads, token):
    with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
        return sorted(pool.map(lambda payload: api(path, 'PATCH', payload, None, token).status_code, payloads))


def login(password):
    return api('auth/login/', 'POST', {'username': 'admin', 'password': password}).json()['access']


def ready():
    # Compose 只判断后端健康；代理 DNS 刷新有短暂的收敛时间。
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if requests.get(BASE + 'health/', timeout=3).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError('反向代理未在 30 秒内恢复健康')


def main():
    for port in [18420, 18421]:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', port))
    FOLDER.mkdir(parents=True)
    password = secrets.token_urlsafe(40)
    environment = {
        'DJANGO_SECRET_KEY': secrets.token_urlsafe(60), 'DB_PASSWORD': secrets.token_urlsafe(40),
        'DB_NAME': 'foundation', 'DB_USER': 'postgres', 'ADMINCORE_ADMIN_PASSWORD': password,
        'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend', 'DJANGO_ENV': 'production',
        'DJANGO_DEBUG': 'False', 'FRONTEND_PORT': '18421', 'BACKEND_PORT': '18420',
        'ALLOW_PUBLIC_REGISTRATION': 'False', 'USE_TLS': 'False',
    }
    env_file = FOLDER / 'fixture.env'
    env_file.write_text(''.join(key + '=' + value + '\n' for key, value in environment.items()), encoding='utf-8')
    override = 'services:\n'
    for service in ['backend', 'worker', 'beat']:
        override += f'  {service}:\n    env_file: !override\n      - {env_file.as_posix()}\n    image: {PROJECT}-backend\n'
    override += f'  frontend:\n    image: {PROJECT}-frontend\n    ports: !override\n      - "127.0.0.1:18421:80"\n'
    (FOLDER / 'override.yml').write_text(override, encoding='utf-8')
    (FOLDER / 'standard.yml').write_text('''services:
  redis:
    profiles: !reset []
  backend:
    environment:
      ADMINCORE_PRESET: standard
      ADMINCORE_MODULES: files,tasks,notifications,data_io,approvals,system,organization
    depends_on: !override
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
''', encoding='utf-8')
    try:
        compose('minimal', 'build', 'backend', 'frontend')
        compose('minimal', 'up', '-d', '--wait', '--wait-timeout', '150', 'db', 'backend', 'frontend')
        services = compose('minimal', 'ps', '--status', 'running', '--services').stdout.split()
        check('精简部署只有数据库、后端、前端', set(services) == {'db', 'backend', 'frontend'})
        api('health/')
        token = login(password)
        check('新初始化账号必须改密', api('auth/me/', token=token).json()['data']['must_change_password'])
        blocked = api('users/', expected=403, token=token).json()
        check('改密前服务端禁止业务访问', blocked['data']['reason'] == 'password_change_required')
        new_password = secrets.token_urlsafe(40)
        api('auth/change_password/', 'POST', {'old_password': password, 'new_password': new_password,
                                            'new_password2': new_password}, token=token)
        api('auth/me/', expected=401, token=token)
        password = new_password
        token = login(password)
        check('改密后解除限制', not api('auth/me/', token=token).json()['data']['must_change_password'])
        competing = [secrets.token_urlsafe(40), secrets.token_urlsafe(40)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            decisions = list(pool.map(lambda candidate: api('auth/change_password/', 'POST', {
                'old_password': password, 'new_password': candidate, 'new_password2': candidate}, None, token).status_code,
                competing))
        check('PostgreSQL 并发改密只有一次成功，旧凭据不能覆盖新密码', sorted(decisions) == [200, 401])
        password = competing[decisions.index(200)]
        token = login(password)
        capabilities = api('modules/', token=token).json()['data']
        check('精简契约关闭全部可选模块', all(not module['enabled'] for module in capabilities['modules']))
        api('system/config/', expected=404, token=token)
        api('files/', expected=404, token=token)
        check('精简部署可编辑本人资料且头像关闭', not api('auth/profile/', token=token).json()['data']['avatar_enabled'])
        api('auth/profile/', 'PATCH', {'profile_version': 1, 'bio': '精简个人资料'}, token=token)
        api('auth/avatar/', expected=404, token=token)
        compose('minimal', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "from apps.core.models import SystemConfig; SystemConfig.objects.create(key='brand.name',value='迁移保留品牌')")
        compose('standard', 'up', '-d', '--wait', '--wait-timeout', '150', 'db', 'redis', 'backend', 'frontend')
        ready()
        token = login(password)
        check('精简库重新启用模块保留历史配置', api('brand/').json()['data']['name'] == '迁移保留品牌')
        version = api('auth/profile/', token=token).json()['data']['profile_version']
        statuses = concurrent_patch('auth/profile/', [{'profile_version': version, 'bio': name} for name in ['窗口甲', '窗口乙']], token)
        check('PostgreSQL 本人资料同版本并发仅一次成功', statuses == [200, 409])
        statuses = concurrent_patch('system/config/files.retention_days/', [{'value': value, 'version': 0} for value in [45, 60, 75, 90]], token)
        check('PostgreSQL 并发首次配置仅一次成功', statuses == [200, 409, 409, 409])
        config = api('system/config/files.retention_days/', token=token).json()['data'][0]
        retained = config['value']
        row = api('system/dictionaries/', 'POST', {'code': 'integration', 'name': '并发测试', 'items': [], 'version': 0}, 201, token).json()['data']
        statuses = concurrent_patch('system/dictionaries/' + row['id'] + '/', [{'name': name, 'version': 1} for name in ['甲', '乙']], token)
        check('PostgreSQL 字典编辑冲突不覆盖', statuses == [200, 409])
        departments = [api('organization/departments/', 'POST', {'name': name, 'version': 0}, 201, token).json()['data'] for name in ['甲部门', '乙部门']]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(api, 'organization/departments/' + departments[index]['id'] + '/', 'PATCH',
                                   {'parent': departments[1-index]['id'], 'version': 1}, None, token) for index in [0, 1]]
            statuses = sorted(future.result().status_code for future in futures)
        check('PostgreSQL 并发部门互相挂载不能形成循环', statuses == [200, 400])
        admin_id = api('auth/me/', token=token).json()['data']['id']
        membership = api('organization/memberships/', 'POST', {'user': admin_id, 'department': departments[0]['id'], 'version': 0}, 201, token).json()['data']
        statuses = concurrent_patch('organization/memberships/' + membership['id'] + '/',
                                    [{'department': department['id'], 'version': 1} for department in departments], token)
        check('PostgreSQL 人员归属编辑冲突不覆盖', statuses == [200, 409])
        role = api('permissions/roles/', 'POST', {'name': '并发范围规则'}, 201, token).json()['data']
        grant = api('organization/scopes/', 'POST', {'role': role['id'], 'resource': 'user', 'scope': 'self', 'version': 0}, 201, token).json()['data']
        statuses = concurrent_patch('organization/scopes/' + grant['id'] + '/',
                                    [{'scope': scope, 'departments': [], 'version': 1} for scope in ['all', 'department']], token)
        check('PostgreSQL 数据范围编辑冲突不覆盖', statuses == [200, 409])
        payload = {'title': '并发幂等申请', 'request_type': 'other', 'content': '只执行一次', 'assignee_id': admin_id}
        headers = {'Idempotency-Key': 'postgres-concurrent-create'}
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: api('approvals/', 'POST', payload, None, token, headers), range(4)))
        check('PostgreSQL 同键并发四次只创建一份申请',
              all(response.status_code == 201 for response in responses)
              and len({response.json()['data']['id'] for response in responses}) == 1
              and sum(response.headers.get('Idempotency-Replayed') == 'true' for response in responses) == 3)
        api('approvals/', 'POST', {**payload, 'title': '不同内容'}, 409, token, headers)
        approval_id = responses[0].json()['data']['id']
        decision_headers = {'Idempotency-Key': 'postgres-concurrent-decision'}
        with ThreadPoolExecutor(max_workers=4) as pool:
            decisions = list(pool.map(lambda _: api(f'approvals/{approval_id}/approve/', 'POST', {'comment': ''}, None, token, decision_headers), range(4)))
        check('PostgreSQL 同键审批决策并发全部重放且只执行一次',
              all(response.status_code == 200 for response in decisions)
              and sum(response.headers.get('Idempotency-Replayed') == 'true' for response in decisions) == 3)
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "from concurrent.futures import ThreadPoolExecutor; from django.db import connections; from apps.core.tasks import dispatch_outbox; from apps.core.models import OutboxEvent; from apps.approvals.models import ApprovalRequest; from apps.notifications.models import Notification; "
                "exec('def drain(_):\\n try:\\n  return dispatch_outbox()\\n finally:\\n  connections.close_all()'); "
                "pool=ThreadPoolExecutor(max_workers=4); list(pool.map(drain, range(4))); pool.shutdown(); "
                "assert ApprovalRequest.objects.filter(title='并发幂等申请').count()==1; "
                "assert OutboxEvent.objects.count()==2 and OutboxEvent.objects.filter(status='succeeded').count()==2; "
                "assert Notification.objects.count()==2")
        check('PostgreSQL 四个派发器并发消费两条事件无重复通知', True)
        import base64
        source = (ROOT / 'scripts/recycle_concurrency.py').read_bytes()
        encoded = base64.b64encode(source).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('PostgreSQL 回收站行锁、版本冲突与恢复/清理竞争', True)
        encoded = base64.b64encode((ROOT / 'scripts/profile_concurrency.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('PostgreSQL 头像绑定/陈旧删除及删除/上传双向竞争', True)
        # 在真实 Nginx/PostgreSQL/本地存储链路上验收二进制预览及模块 worker MIME。
        import io
        from PIL import Image
        from pypdf import PdfWriter
        png = io.BytesIO()
        Image.new('RGB', (16, 16), 'blue').save(png, format='PNG')
        version = api('auth/profile/', token=token).json()['data']['profile_version']
        for offset in [0, 1]:
            avatar = requests.post(BASE + 'auth/avatar/', files={'file': ('avatar.png', png.getvalue(), 'image/png')},
                                   data={'profile_version': version + offset}, headers={'Authorization': 'Bearer ' + token}, timeout=20)
            check('真实 HTTP 本人头像上传/替换 ' + str(offset), avatar.status_code == 200 and avatar.json()['data']['has_avatar'])
        avatar = api('auth/avatar/', token=token)
        check('真实 Nginx 私有头像响应和归一化尺寸', avatar.headers['Content-Type'] == 'image/png'
              and avatar.headers['Cache-Control'] == 'private, no-store' and avatar.headers['X-Content-Type-Options'] == 'nosniff'
              and Image.open(io.BytesIO(avatar.content)).size == (256, 256))
        api('auth/avatar/', expected=401)
        api('auth/avatar/', 'DELETE', {'profile_version': version + 1}, 409, token)
        api('auth/avatar/', 'DELETE', {'profile_version': version + 2}, token=token)
        api('auth/avatar/', expected=404, token=token)
        check('头像不进入普通文件回收站', api('files/recycle/', token=token).json()['data']['pagination']['total'] == 0)
        pdf = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        writer.write(pdf)
        for name, content, mime in [('private.png', png.getvalue(), 'image/png'), ('private.pdf', pdf.getvalue(), 'application/pdf')]:
            response = requests.post(BASE + 'files/', files={'file': (name, content, mime)},
                                     headers={'Authorization': 'Bearer ' + token}, timeout=20)
            check('真实 HTTP 上传预览夹具 ' + name, response.status_code == 201)
            preview_path = f"files/{response.json()['id']}/preview/"
            preview = api(preview_path, token=token)
            check('预览内容类型/私有无缓存/安全响应头 ' + name,
                  preview.headers['Content-Type'] == mime and preview.headers['Cache-Control'] == 'private, no-store'
                  and preview.headers['X-Content-Type-Options'] == 'nosniff'
                  and 'sandbox' in preview.headers['Content-Security-Policy'] and len(preview.content) > 0)
            api(preview_path, expected=401)
        origin = BASE.removesuffix('/api/v1/')
        manifest = requests.get(origin + '/.vite/manifest.json', timeout=10).json()
        worker = manifest['node_modules/pdfjs-dist/build/pdf.worker.min.mjs']['file']
        worker_response = requests.get(origin + '/' + worker, timeout=10)
        check('真实 Nginx 模块 worker 使用 JavaScript MIME', worker_response.status_code == 200
              and worker_response.headers['Content-Type'].startswith('application/javascript'))
        check('生产 CSP 允许同源 worker 且禁止 eval', "worker-src 'self'" in worker_response.headers['Content-Security-Policy']
              and "'unsafe-eval'" not in worker_response.headers['Content-Security-Policy'])
        upload = requests.post(BASE + 'files/', files={'file': ('recycle-live.txt', b'live-fixture', 'text/plain')},
                               headers={'Authorization': 'Bearer ' + token}, timeout=20)
        check('真实 HTTP 文件上传', upload.status_code == 201)
        # 上传保留已有非分页响应格式，分页接口使用统一 data 包装。
        uploaded = upload.json()
        file_id = uploaded['id']
        api(f'files/{file_id}/', 'DELETE', expected=204, token=token)
        trashed = api('files/recycle/', token=token).json()['data']['items'][0]
        check('真实 HTTP 回收站保留删除操作者和版本', trashed['deleted_by'] == admin_id and trashed['lifecycle_version'] == 2)
        policy = api('files/recycle_policy/', token=token).json()['data']
        check('真实 HTTP 保留期跟随配置且定时计划已启用', policy['retention_days'] == retained and policy['cleanup_enabled'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: api(f'files/{file_id}/restore/', 'POST', {'lifecycle_version': 2}, None, token), range(2)))
        check('真实 HTTP 同版本恢复仅一次成功', sorted(response.status_code for response in responses) == [200, 409])
        downloaded = api(f'files/{file_id}/download/', token=token)
        check('恢复后鉴权下载字节不变', downloaded.content == b'live-fixture')
        api(f'files/{file_id}/', 'DELETE', expected=204, token=token)
        preview = api('files/recycle_action/', 'POST', {'action': 'purge', 'dry_run': True,
                      'items': [{'id': file_id, 'lifecycle_version': 4}]}, token=token).json()['data']
        check('真实 HTTP 删除预览不删除回收站文件', preview['succeeded'] == 1 and preview['dry_run'])
        compose('minimal', 'up', '-d', '--wait', '--wait-timeout', '150', 'backend', 'frontend')
        ready()
        token = login(password)
        api('organization/departments/', expected=404, token=token)
        api('system/dictionaries/', expected=404, token=token)
        api('files/recycle/', expected=404, token=token)
        api(f'files/{file_id}/restore/', 'POST', {'lifecycle_version': 4}, 404, token)
        compose('minimal', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "from apps.core.modules import task_enabled; assert not task_enabled('data_io.run_data_import'); from apps.core.models import DataDictionary; assert DataDictionary.objects.filter(code='integration').exists()")
        compose('standard', 'up', '-d', '--wait', '--wait-timeout', '150', 'backend', 'frontend')
        ready()
        token = login(password)
        check('关闭并重新启用后参数与字典数据保留', api('system/config/files.retention_days/', token=token).json()['data'][0]['value'] == retained
              and api('system/dictionaries/options/integration/', token=token).json()['data']['version'] == 2)
        check('文件模块关闭/重新启用保留回收站记录', api('files/recycle/', token=token).json()['data']['items'][0]['id'] == file_id)
        check('当前迁移无遗漏', compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'makemigrations', '--check', '--dry-run').returncode == 0)
        command = ['docker', 'compose', '-p', PROJECT, '--env-file', str(env_file), '-f', 'docker-compose.yml',
                   '-f', 'compose.minimal.yml', '-f', str(FOLDER / 'override.yml'), '-f', str(FOLDER / 'standard.yml')]
        for key, value, label in [('ADMINCORE_PRESET', 'demo', '生产配置拒绝演示预设'), ('ADMINCORE_MODULES', 'approvals', '缺失模块依赖立即拒绝启动')]:
            result = run(command + ['exec', '-T', '-e', key + '=' + value, 'backend', 'python', '-c',
                                    'from django.conf import settings; print(settings.ADMINCORE_MODULES)'], allowed_failure=True)
            check(label, result.returncode != 0 and 'ImproperlyConfigured' in result.stderr)
        report = {'project': PROJECT, 'checks': CHECKS, 'passed': True, 'ports': [18420, 18421], 'postgres': '18.6', 'finished_at': time.strftime('%Y-%m-%d %H:%M:%S')}
        (FOLDER / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        compose('standard', 'down', '--volumes')
        env_file.unlink()
        print('独立验收完成，容器和测试卷已清理；报告：' + str(FOLDER / 'report.json'))
    except Exception as exc:
        (FOLDER / 'report.json').write_text(json.dumps({'project': PROJECT, 'checks': CHECKS, 'passed': False, 'error': str(exc)}, ensure_ascii=False, indent=2), encoding='utf-8')
        print('失败证据与隔离项目保留：' + str(FOLDER), file=sys.stderr)
        raise


if __name__ == '__main__':
    main()
