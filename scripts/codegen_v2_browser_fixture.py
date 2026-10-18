"""V2 浏览器验收的独占 SQLite/前端副本；不复用现有服务或管理员凭据。"""
import json
import os
from pathlib import Path
import secrets
import signal
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def validate_browser(folder, work, env, *, build=True):
    if folder.resolve().parent != (ROOT / '.codex-validation').resolve() or not folder.name.startswith('codegen-v2-'):
        raise RuntimeError('浏览器夹具路径不在任务临时目录内')
    for port in (18471, 18472):
        with socket.socket() as listener:
            # Linux 连续运行两轮验收时，已关闭连接可能仍处于 TIME_WAIT。
            # 与 Django/Vite 的监听行为一致；仍拒绝已被其他服务监听的端口。
            if os.name != 'nt':
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', port))
    front = folder / 'frontend'
    ignored = shutil.ignore_patterns('node_modules', 'dist', 'coverage', 'test-results',
                                    'playwright-report', '.env*', '*.log')
    shutil.copytree(ROOT / 'frontend', front, ignore=ignored, dirs_exist_ok=True)
    shutil.copytree(work / 'frontend', front, dirs_exist_ok=True)
    (folder / '.env').write_text('# isolated browser fixture\n', encoding='utf-8')
    registry = front / 'src/modules/registry.ts'
    source = registry.read_text(encoding='utf-8')
    anchor = 'export const frontendExtensions = ['
    if source.count(anchor) != 1:
        raise RuntimeError('前端显式注册入口已变化')
    entries = ','.join('{key:%s,path:%s,permission:%s,title:%s,component:()=>import(%s)}' % (
        json.dumps(key), json.dumps('/' + key.replace('_', '-')), json.dumps(key + ':read'),
        json.dumps(title, ensure_ascii=False), json.dumps('../views/' + key + '/RecordListView.vue'))
        for key, title in [('cg_suppliers', '供应商'), ('cg_categories', '商品分类'), ('cg_orders', '采购订单')])
    registry.write_text(source.replace(anchor, anchor + entries + ',', 1), encoding='utf-8')
    config = front / 'vite.config.ts'
    source = (ROOT / 'frontend/vite.config.ts').read_text(encoding='utf-8')
    if source.count("target: 'http://localhost:8000'") != 1:
        raise RuntimeError('前端代理入口已变化')
    config.write_text(source.replace("target: 'http://localhost:8000'", "target: 'http://127.0.0.1:18472'")
                      .replace('open: true', 'open: false'), encoding='utf-8')
    settings = (folder / 'codegen_v2_settings.py').read_text(encoding='utf-8').split('\nDATABASES =')[0]
    settings += f"\nDATABASES = {{'default': {{'ENGINE': 'django.db.backends.sqlite3', 'NAME': {str(folder / 'browser.sqlite3')!r}}}}}\n"
    settings += "AUTH_LOGIN_CAPTCHA_ENABLED = False\nALLOWED_HOSTS = ['127.0.0.1', 'localhost']\n"
    # 一次整合覆盖几十个模块并轮询任务，会超过单用户正常每小时预算。
    # 仅提高此独占夹具的通用请求预算；专用登录/验证/凭证限流保留原值。
    settings += "REST_FRAMEWORK = {**REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': {'anon': '1000/hour', 'user': '100000/hour'}}\n"
    # 独占夹具无 worker；脚本在提交后调用真实任务，覆盖等待、变更失败与取消。
    settings += "CELERY_TASK_ALWAYS_EAGER = False\nCELERY_BROKER_URL = 'memory://'\n"
    settings += f"MEDIA_ROOT = {str(folder / 'browser-media')!r}\n"
    settings += "ADMINCORE_MODULES = (*ADMINCORE_MODULES, 'online_forms', 'api_credentials')\n"
    (folder / 'codegen_browser_settings.py').write_text(settings, encoding='utf-8')
    env = {**env, 'DJANGO_SETTINGS_MODULE': 'codegen_browser_settings', 'VITE_AUTH_SESSION_TRANSPORT': 'bearer',
           'ADMINCORE_VALIDATION_PYTHON': sys.executable, 'ADMINCORE_VALIDATION_BACKEND': str(ROOT / 'backend')}
    node_bin = ROOT / '.codex-validation/toolchains/node-v24.21.0-win-x64'
    bundled = os.name == 'nt' and (node_bin / 'node.exe').exists()
    node = str(node_bin / 'node.exe') if bundled else shutil.which('node')
    npm = [node, str(node_bin / 'node_modules/npm/bin/npm-cli.js')] if bundled else [shutil.which('npm')]
    env['PATH'] = (str(node_bin) + os.pathsep if bundled else '') + env.get('PATH', '')
    temp = folder / 'browser-temp'; temp.mkdir(exist_ok=True)
    env.update(TEMP=str(temp), TMP=str(temp))
    processes = []
    handles = []
    report = {'passed': False, 'production_build': build, 'ports': [18471, 18472], 'stopped_pids': []}

    def run(command, log, cwd=ROOT / 'backend', input=None):
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=600, input=input)
        (folder / log).write_text(result.stdout + result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError('浏览器验收失败，见 ' + str(folder / log))

    def start(command, log, cwd):
        handle = (folder / log).open('w', encoding='utf-8'); handles.append(handle)
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                   start_new_session=os.name != 'nt')
        processes.append(process)
        return process

    def ready(url, process):
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError('隔离服务提前退出')
            try:
                with urlopen(url, timeout=2) as response:
                    if response.status < 400:
                        return
            except (URLError, OSError):
                time.sleep(0.3)
        raise RuntimeError('隔离服务未就绪')

    try:
        if not (front / 'node_modules').is_dir():
            run([*npm, 'ci', '--ignore-scripts'], 'browser-npm.log', front)
        if build:
            run([*npm, 'run', 'build'], 'browser-build.log', front)
        database = folder / 'browser.sqlite3'
        if database.exists():
            # 仅保留上一次的隔离夹具，重试使用新数据库。
            database.rename(folder / ('browser-previous-' + secrets.token_hex(4) + '.sqlite3'))
        run([sys.executable, 'manage.py', 'migrate', '--noinput'], 'browser-migrate.log')
        password = secrets.token_urlsafe(40)
        access = folder / 'browser-access.json'
        access.write_text(json.dumps({'password': password}), encoding='utf-8')
        seed = '''import django, json, os
django.setup()
from django.contrib.auth import get_user_model
from django.core.management import call_command
from apps.core.models import DataDictionary
from apps.cg_suppliers.models import Supplier
from apps.cg_orders import extensions
from decimal import Decimal
password = json.loads(open(os.environ['CODEGEN_BROWSER_ACCESS'], encoding='utf-8').read())['password']
user = get_user_model().objects.create_superuser(username='admin', password=password, email='fixture@example.invalid', must_change_password=False)
call_command('bootstrap_admincore')
DataDictionary.objects.create(code='purchase_category', name='采购类别', items=[{'value':'office','label':'办公','is_active':True}])
Supplier.objects.create(code='S-1', name='隔离供应商', creator=user)
'''
        env['CODEGEN_BROWSER_ACCESS'] = str(access)
        if env.get('ADMINCORE_STAGE3') == '1':
            seed += '''
from apps.approvals.models import ApprovalFlow
from apps.permissions.models import Role, UserRole
from pathlib import Path
definition = json.loads((Path(os.environ['ADMINCORE_INTEGRATION_EXAMPLES']) / 'purchase-flow.json').read_text(encoding='utf-8'))
for node in definition['nodes']:
    if node['type'] == 'user':
        role = Role.objects.create(name='fixture-' + node['id'])
        UserRole.objects.create(user=user, role=role)
        node['assignee']['role_id'] = str(role.pk)
ApprovalFlow.objects.create(name='采购金额审批', code='purchase-approval', definition=definition, created_by=user)
'''
        run([sys.executable, '-X', 'utf8', '-c', seed], 'browser-seed.log')
        extension = work / 'backend/apps/cg_orders/extensions.py'
        extension.write_text('''from decimal import Decimal
def before_save(*, actor, instance, values, details):
    if 'lines' in details:
        values['amount'] = sum((Decimal(line['price']) * line['quantity'] for line in details['lines']), Decimal('0'))
def after_save(*, actor, instance, action):
    pass
def before_delete(*, actor, instance):
    pass
''', encoding='utf-8')
        backend = start([sys.executable, 'manage.py', 'runserver', '127.0.0.1:18472', '--noreload'], 'browser-backend.log', ROOT / 'backend')
        ready('http://127.0.0.1:18472/api/v1/auth/recovery/config/', backend)
        frontend = start([node, 'node_modules/vite/bin/vite.js', *(['preview'] if build else []), '--host', '127.0.0.1', '--port', '18471', '--strictPort'], 'browser-frontend.log', front)
        ready('http://127.0.0.1:18471', frontend)
        script = 'business_integration_browser.mjs' if env.get('ADMINCORE_STAGE3') == '1' else 'codegen_v2_browser.mjs'
        run([node, str(ROOT / 'scripts' / script), str(front), str(folder)], 'browser-run.log', front)
        report['passed'] = True
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=15)
            report['stopped_pids'].append(process.pid)
        for handle in handles:
            handle.close()
        report['ports_released'] = []
        for port in report['ports']:
            with socket.socket() as listener:
                listener.settimeout(0.2)
                if listener.connect_ex(('127.0.0.1', port)) != 0:
                    report['ports_released'].append(port)
        if report['ports_released'] != report['ports']:
            report['passed'] = False
        (folder / 'browser-access.json').unlink(missing_ok=True)
        if report['passed']:
            # 依赖保留，成功运行的源码/构建/夹具数据不作为交付内容。
            cleaned = []
            for child in front.iterdir():
                if child.name != 'node_modules':
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
                    cleaned.append(str(child))
            for name in ['browser.sqlite3', 'browser-media', 'browser-temp']:
                path = folder / name
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
                cleaned.append(str(path))
            report['cleaned'] = cleaned
        (folder / 'browser-fixture-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if not report['passed']:
        raise RuntimeError('浏览器夹具未完整通过或测试端口未释放')
