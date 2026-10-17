"""独占数据库和端口验收在线表单 V2，不读取部署凭据或连接已有业务库。"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--postgres', action='store_true')
    args = parser.parse_args()
    folder = ROOT / '.codex-validation' / ('online-forms-v2-' + uuid.uuid4().hex[:10])
    folder.mkdir(parents=True)
    env = {key: value for key, value in os.environ.items() if not key.startswith(
        ('ADMINCORE_', 'AUTH_', 'DJANGO_', 'DB_', 'SSO_', 'CELERY_', 'REDIS_', 'EMAIL_', 'SMTP_', 'AWS_', 'VITE_'))}
    env.update(PYTHON_DOTENV_DISABLED='1', PYTHONUTF8='1', DJANGO_ENV='testing',
               DJANGO_SETTINGS_MODULE='online_forms_browser_settings', PYTHONPATH=str(folder) + os.pathsep + str(ROOT / 'backend'),
               ADMINCORE_MODULES='system,online_forms', VITE_AUTH_SESSION_TRANSPORT='bearer')
    temp = folder / 'temp'; temp.mkdir()
    env.update(TEMP=str(temp), TMP=str(temp))
    node_bin = ROOT / '.codex-validation/toolchains/node-v24.21.0-win-x64'
    bundled = os.name == 'nt' and (node_bin / 'node.exe').exists()
    node = str(node_bin / 'node.exe') if bundled else shutil.which('node')
    env['PATH'] = (str(node_bin) + os.pathsep if bundled else '') + env.get('PATH', '')
    npm = [node, str(node_bin / 'node_modules/npm/bin/npm-cli.js')] if bundled else [shutil.which('npm')]
    processes, handles = [], []
    report = {'passed':False, 'ports':[18481,18482], 'stopped_pids':[]}
    container, container_started = None, False

    def run(command, log, cwd=ROOT / 'backend', input=None):
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=600, input=input)
        (folder / log).write_text(result.stdout + result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError('验收失败：' + str(folder / log))

    def start(command, log, cwd):
        handle = (folder / log).open('w', encoding='utf-8'); handles.append(handle)
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, start_new_session=os.name != 'nt')
        processes.append(process)
        return process

    def ready(url, process):
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError('验收服务提前退出')
            try:
                with urlopen(url, timeout=2) as response:
                    if response.status < 400:
                        return
            except (URLError, OSError):
                time.sleep(0.3)
        raise RuntimeError('验收服务未就绪')

    try:
        for port in report['ports']:
            with socket.socket() as listener:
                listener.bind(('127.0.0.1',port))
        database = "DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': %r}}\n" % str(folder / 'browser.sqlite3')
        report['database'] = 'sqlite'
        if args.postgres:
            container = 'admincore-ofv2-' + folder.name.removeprefix('online-forms-v2-')
            with socket.socket() as listener:
                listener.bind(('127.0.0.1',0)); port=listener.getsockname()[1]
            db_password=secrets.token_urlsafe(40)
            (folder/'postgres.env').write_text('POSTGRES_DB=online_forms_v2\nPOSTGRES_PASSWORD='+db_password+'\n',encoding='utf-8')
            run(['docker','run','-d','--name',container,'--env-file',str(folder/'postgres.env'),'-p',f'127.0.0.1:{port}:5432','postgres:18.6'],'postgres-start.log')
            container_started=True
            for _ in range(60):
                result=subprocess.run(['docker','exec',container,'psql','-U','postgres','-d','online_forms_v2','-Atc','SELECT 1'],capture_output=True)
                if result.returncode == 0:
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError('独占PostgreSQL未就绪')
            env['ONLINE_FORMS_PG_PASSWORD']=db_password
            database = "DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'online_forms_v2', 'USER': 'postgres', 'PASSWORD': __import__('os').environ['ONLINE_FORMS_PG_PASSWORD'], 'HOST': '127.0.0.1', 'PORT': %d}}\n" % port
            report['database']='postgresql'
        settings = 'from config.settings.testing import *\n' + database
        settings += f"MEDIA_ROOT = {str(folder / 'media')!r}\nAUTH_LOGIN_CAPTCHA_ENABLED = False\nALLOWED_HOSTS = ['127.0.0.1','localhost']\n"
        (folder/'online_forms_browser_settings.py').write_text(settings,encoding='utf-8')
        # 前端副本排除环境文件；依赖独立安装并在成功后保留以便复核。
        front=folder/'frontend'
        shutil.copytree(ROOT/'frontend',front,ignore=shutil.ignore_patterns('node_modules','dist','coverage','test-results','playwright-report','.env*','*.log'))
        config=front/'vite.config.ts'
        source=config.read_text(encoding='utf-8')
        if source.count("target: 'http://localhost:8000'") != 1:
            raise RuntimeError('前端代理配置已变化')
        config.write_text(source.replace("target: 'http://localhost:8000'","target: 'http://127.0.0.1:18482'").replace('open: true','open: false'),encoding='utf-8')
        run([*npm,'ci','--ignore-scripts'],'npm.log',front)
        run([*npm,'run','build'],'build.log',front)
        run([sys.executable,'manage.py','migrate','--noinput'],'migrate.log')
        access=folder/'access.json'
        access.write_text(json.dumps({'password':secrets.token_urlsafe(40)}),encoding='utf-8')
        env['ONLINE_FORMS_ACCESS_FILE']=str(access)
        run([sys.executable,'-X','utf8','-c',"""import django,json,os
django.setup()
from django.contrib.auth import get_user_model
from django.core.management import call_command
password=json.load(open(os.environ['ONLINE_FORMS_ACCESS_FILE'],encoding='utf-8'))['password']
get_user_model().objects.create_superuser(username='admin',password=password,email='fixture@example.invalid',must_change_password=False)
call_command('bootstrap_admincore')
"""],'seed.log')
        if args.postgres:
            run([sys.executable,'-m','pytest','tests/test_online_forms.py','tests/test_online_forms_v2.py',
                 '--ds=online_forms_browser_settings','--create-db','-q'],'postgres-tests.log')
        backend=start([sys.executable,'manage.py','runserver','127.0.0.1:18482','--noreload'],'backend.log',ROOT/'backend')
        ready('http://127.0.0.1:18482/api/v1/auth/recovery/config/',backend)
        frontend=start([node,'node_modules/vite/bin/vite.js','preview','--host','127.0.0.1','--port','18481','--strictPort'],'frontend.log',front)
        ready('http://127.0.0.1:18481',frontend)
        run([node,str(ROOT/'scripts/online_forms_v2_browser.mjs'),str(front),str(folder)],'browser.log',front)
        report['passed']=True
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                else:
                    os.killpg(process.pid,signal.SIGTERM)
                process.wait(timeout=15)
            report['stopped_pids'].append(process.pid)
        for handle in handles:
            handle.close()
        report['ports_released']=[]
        for port in report['ports']:
            with socket.socket() as listener:
                if listener.connect_ex(('127.0.0.1',port)) != 0:
                    report['ports_released'].append(port)
        if report['ports_released'] != report['ports']:
            report['passed']=False
        for filename in ['access.json','postgres.env']:
            (folder/filename).unlink(missing_ok=True)
        if container_started:
            result=subprocess.run(['docker',*(['rm','-f','-v',container] if report['passed'] else ['stop',container])],capture_output=True)
            report['container_removed']=report['passed'] and result.returncode == 0
            if result.returncode:
                report['passed']=False
            report['container']=container
        if report['passed']:
            # 仅此 UUID 目录内已成功验收的夹具；失败时完整保留源码、日志与数据库。
            if folder.resolve().parent != (ROOT/'.codex-validation').resolve() or not folder.name.startswith('online-forms-v2-'):
                raise RuntimeError('拒绝清理工作区外路径')
            cleaned=[]
            for child in front.iterdir():
                if child.name != 'node_modules':
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
                    cleaned.append(str(child))
            for name in ['temp','media','browser.sqlite3']:
                path=folder/name
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
                cleaned.append(str(path))
            report['cleaned']=cleaned
        (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({'evidence':str(folder),**report},ensure_ascii=False),flush=True)
    if not report['passed']:
        raise RuntimeError('在线表单浏览器验收未完成')


if __name__ == '__main__':
    main()
