"""三服务隔离验收图片处理：真实 HTTP/PostgreSQL/Nginx/浏览器，不连接正式库。"""
from pathlib import Path
import io
import json
import os
import secrets
import shutil
import socket
import subprocess
import time
import uuid

import requests
from PIL import Image
from image_capacity import measure

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'admincore-images-' + uuid.uuid4().hex[:8]
FOLDER = ROOT / '.codex-validation' / PROJECT
PORTS = [18460, 18461]
BASE = 'http://127.0.0.1:18461/api/v1/'
CHECKS = []


def run(arguments, *, input=None, allowed_failure=False):
    result = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True, input=input,
                            encoding='utf-8', errors='replace', timeout=360)
    with (FOLDER / 'contract.log').open('a', encoding='utf-8') as log:
        log.write(result.stdout + result.stderr)
    if result.returncode and not allowed_failure:
        raise RuntimeError('图片隔离验收失败，见 contract.log')
    return result


def compose(mode, *arguments, input=None, allowed_failure=False):
    command = ['docker', 'compose', '-p', PROJECT, '--env-file', str(FOLDER / 'fixture.env')]
    for file in ['docker-compose.yml', 'compose.minimal.yml', str(FOLDER / 'override.yml')]:
        command += ['-f', file]
    if mode in {'on', 'sync'}: command += ['-f', str(FOLDER / 'on.yml')]
    if mode == 'sync': command += ['-f', str(FOLDER / 'sync.yml')]
    return run(command + list(arguments), input=input, allowed_failure=allowed_failure)


def check(label, condition=True):
    if not condition: raise AssertionError(label)
    CHECKS.append(label); print('通过：' + label, flush=True)


def snippet(code, mode='on'):
    prefix = "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); import django; django.setup(); from django.conf import settings; assert settings.DATABASES['default']['NAME']=='images_fixture'\n"
    return compose(mode, 'exec', '-T', 'backend', 'python', '-c', 'import sys; exec(sys.stdin.read())', input=prefix + code).stdout.strip()


def api(path, token=None, method='GET', data=None, files=None, expected=200):
    response = requests.request(method, BASE + path,
        headers={'Authorization': 'Bearer ' + token} if token else {},
        **({'data': data, 'files': files} if files else {'json': data}), timeout=30)
    check(method + ' ' + path + ' → ' + str(expected), response.status_code == expected)
    return response


def ready():
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if requests.get(BASE + 'health/', timeout=2).status_code == 200: return
        except requests.RequestException: pass
        time.sleep(0.2)
    raise RuntimeError('图片隔离服务未就绪')


def image_capacity(password, profile):
    snippet("from django.contrib.auth import get_user_model\n"
            "for index in range(4): get_user_model().objects.create_superuser('capacity-" + profile + "-'+str(index), "
            "password=" + repr(password) + ", must_change_password=False)")
    actors = []
    source = io.BytesIO()
    with Image.linear_gradient('L') as gradient:
        with gradient.resize((4000, 4000)) as large:
            with large.convert('RGB') as image:
                image.save(source, 'JPEG', quality=90)
    content = source.getvalue()
    for index in range(4):
        token = api('auth/login/', method='POST', data={'username': 'capacity-' + profile + '-' + str(index),
                                                      'password': password}).json()['access']
        row = api('files/', token, 'POST', files={'file': ('capacity.jpg', content, 'image/jpeg')}, expected=201).json()
        actors.append((token, row['id']))
    identifier = compose('on', 'ps', '-q', 'backend').stdout.strip()

    def snapshot():
        # cgroup v2 的累计峰值比低频 docker stats 采样更可靠；观察进程本身也计入 cgroup。
        code = """import json
from pathlib import Path
root=Path('/sys/fs/cgroup')
def counters(name):
    return {key:int(value) for key,value in (line.split() for line in (root/name).read_text().splitlines())}
print(json.dumps({'memory_current':int((root/'memory.current').read_text()),
 'memory_peak':int((root/'memory.peak').read_text()), 'memory_max':int((root/'memory.max').read_text()),
 'cpu_max':(root/'cpu.max').read_text().strip(), 'memory_events':counters('memory.events'),
 'cpu':counters('cpu.stat')}))"""
        result = json.loads(run(['docker', 'exec', identifier, 'python', '-c', code]).stdout)
        state = json.loads(run(['docker', 'inspect', '--format',
            '{"running":{{.State.Running}},"oom_killed":{{.State.OOMKilled}},"restart_count":{{.RestartCount}},"command":{{json .Config.Cmd}}}',
            identifier]).stdout)
        result.update(state)
        check('容量容器实际使用1536MiB/1CPU限制', result['memory_max'] == 1536 * 1024 * 1024
              and result['cpu_max'].split() == ['100000', '100000'])
        command = result['command']
        check('容量容器实际worker/线程参数匹配档位',
              command[command.index('--workers') + 1] == ('3' if profile == 'sync' else '1')
              and command[command.index('--threads') + 1] == ('1' if profile == 'sync' else '4'))
        return result

    runtime = '3进程1线程（同步worker）' if profile == 'sync' else '1进程4线程'
    report = measure(BASE, actors, snapshot, FOLDER / ('capacity-' + profile + '-report.json'), runtime=runtime)
    check('16MP图片48次HTTP变换、逐级并发及同身份锁竞争均正确且无OOM/重启', report['passed'])
    for token, identifier in actors:
        check('容量验收后原件仍完整', api('files/' + identifier + '/download/', token).content == content)
    return report


def main():
    for port in PORTS:
        with socket.socket() as listener: listener.bind(('127.0.0.1', port))
    FOLDER.mkdir(parents=True)
    password, changed = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
    env_file = FOLDER / 'fixture.env'
    environment = {'DJANGO_SECRET_KEY': secrets.token_urlsafe(60), 'DB_PASSWORD': secrets.token_urlsafe(40),
        'DB_NAME': 'images_fixture', 'DB_USER': 'postgres', 'ADMINCORE_ADMIN_PASSWORD': password,
        'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend', 'DJANGO_ENV': 'production', 'DJANGO_DEBUG': 'False',
        'BACKEND_PORT': '18460', 'FRONTEND_PORT': '18461', 'AUTH_LOGIN_CAPTCHA_ENABLED': 'False', 'USE_TLS': 'False'}
    env_file.write_text(''.join(key + '=' + value + '\n' for key, value in environment.items()), encoding='utf-8')
    (FOLDER / 'override.yml').write_text(f'''services:
  backend:
    image: {PROJECT}-backend
    env_file: !override
      - "{env_file.as_posix()}"
    environment:
      ADMINCORE_MODULES: files
      ADMINCORE_IMAGE_PROCESSING_ENABLED: "False"
  frontend:
    image: {PROJECT}-frontend
    ports: !override
      - "127.0.0.1:18461:80"
''', encoding='utf-8')
    (FOLDER / 'on.yml').write_text('services:\n  backend:\n    mem_limit: 1536m\n    cpus: 1.0\n'
        '    environment:\n      ADMINCORE_IMAGE_PROCESSING_ENABLED: "True"\n', encoding='utf-8')
    (FOLDER / 'sync.yml').write_text('services:\n  backend:\n'
        '    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --threads 1 --timeout 60\n', encoding='utf-8')
    report = {'passed': False, 'project': PROJECT, 'ports': PORTS}
    try:
        compose('off', 'build', 'backend', 'frontend')
        compose('off', 'up', '-d', '--wait', '--wait-timeout', '150', 'db', 'backend', 'frontend'); ready()
        check('仅 PostgreSQL/后端/前端，无队列或转换服务', set(compose('off', 'ps', '--status', 'running', '--services').stdout.split()) == {'db', 'backend', 'frontend'})
        token = api('auth/login/', method='POST', data={'username': 'admin', 'password': password}).json()['access']
        api('auth/change_password/', token, 'POST', {'old_password': password, 'new_password': changed, 'new_password2': changed})
        admin_pair = api('auth/login/', method='POST', data={'username': 'admin', 'password': changed}).json()
        token = admin_pair['access']
        source = io.BytesIO()
        Image.new('RGB', (240, 160), 'blue').save(source, 'PNG')
        original = source.getvalue()
        row = api('files/', token, 'POST', files={'file': ('隔离图片.png', original, 'image/png')}, expected=201).json()
        path = 'files/' + row['id'] + '/transform/'
        check('默认关闭能力', api('files/processing_config/', token).json()['data']['enabled'] is False)
        api(path, token, 'POST', {'lifecycle_version': 1}, expected=404)
        compose('on', 'up', '-d', '--wait', '--wait-timeout', '150', 'backend', 'frontend'); ready()
        check('显式开启后可处理', api('files/processing_config/', token).json()['data']['enabled'] is True)
        for format in ['png', 'jpeg', 'webp']:
            result = api(path, token, 'POST', {'lifecycle_version': 1, 'width': 80, 'height': 80, 'format': format},
                         files={'watermark': ('mark.png', original, 'image/png')})
            with Image.open(io.BytesIO(result.content)) as image:
                check('真实编码 ' + format, image.size == (80, 53) and image.format == format.upper())
            check('处理响应禁止缓存和嗅探 ' + format, result.headers['Cache-Control'] == 'private, no-store' and result.headers['X-Content-Type-Options'] == 'nosniff')
        api(path, token, 'POST', {'lifecycle_version': 2}, expected=409)
        api(path, token, 'POST', {'lifecycle_version': 1, 'width': 99999}, expected=400)
        check('原始内容未变化', api('files/' + row['id'] + '/download/', token).content == original)
        (FOLDER / 'browser-access.json').write_text(json.dumps({'password': changed}), encoding='utf-8')
        node_bin = ROOT / '.codex-validation/toolchains/node-v24.21.0-win-x64/node.exe'
        node = str(node_bin) if os.name == 'nt' and node_bin.exists() else shutil.which('node')
        if not node: raise RuntimeError('真实浏览器验收需要 Node.js')
        run([node, str(ROOT / 'scripts/image_browser.mjs'), str(ROOT / 'frontend'), str(FOLDER)])
        check('桌面/手机真实登录、变换、水印、下载和草稿守卫')
        snippet((ROOT / 'scripts/image_concurrency.py').read_text(encoding='utf-8'))
        check('PostgreSQL 锁等待后的账号/设备/双权限/范围/版本/删除复核')
        report['capacity'] = {'threaded': image_capacity(changed, 'threaded')}
        compose('sync', 'up', '-d', '--wait', '--wait-timeout', '150', 'backend'); ready()
        report['capacity']['sync'] = image_capacity(changed, 'sync')
        # 容量阶段可能超过 access 的5分钟寿命；真实轮换后进入关闭/恢复验收。
        token = api('auth/refresh/', method='POST', data={'refresh': admin_pair['refresh']}).json()['data']['access']
        retained = snippet("from apps.files.models import FileModel; import hashlib; r=FileModel.objects.get(pk=" + repr(row['id']) + "); print(hashlib.sha256(r.file.read()).hexdigest())")
        compose('off', 'up', '-d', '--wait', '--wait-timeout', '150', 'backend'); ready()
        api(path, token, 'POST', {'lifecycle_version': 1}, expected=404)
        check('关闭后原件可下载', api('files/' + row['id'] + '/download/', token).content == original)
        compose('on', 'up', '-d', '--wait', '--wait-timeout', '150', 'backend'); ready()
        api(path, token, 'POST', {'lifecycle_version': 1})
        check('重新启用保留原件摘要', retained == snippet("from apps.files.models import FileModel; import hashlib; r=FileModel.objects.get(pk=" + repr(row['id']) + "); print(hashlib.sha256(r.file.read()).hexdigest())"))
        compose('on', 'exec', '-T', 'backend', 'python', 'manage.py', 'spectacular', '--validate', '--fail-on-warn', '--file', '/tmp/images-schema.yml')
        check('实际启用配置 OpenAPI 检查通过')
        report['passed'] = True
    finally:
        report['checks'] = CHECKS
        if report['passed']:
            compose('on', 'down', '-v', '--remove-orphans')
            run(['docker', 'image', 'rm', PROJECT + '-backend', PROJECT + '-frontend'])
            for name in ['fixture.env', 'browser-access.json']: (FOLDER / name).unlink(missing_ok=True)
            report['cleaned'] = ['isolated containers, volumes and image tags', 'fixture credentials']
        else:
            compose('on', 'logs', '--no-color', allowed_failure=True)
            compose('on', 'stop', allowed_failure=True)
        (FOLDER / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'evidence': str(FOLDER), **report}, ensure_ascii=False), flush=True)


if __name__ == '__main__': main()
