"""下载经 SHA-256 校验的官方 MinIO 程序，隔离验收实际 S3 协议。

只启动本任务的进程；凭据随机且仅存在于子进程环境，不访问正式桶。
"""
import hashlib
import argparse
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = 'RELEASE.2025-09-07T16-13-09Z'
ASSETS = {
    'Windows': ('minio.windows-amd64.' + RELEASE + '.exe',
                'af709e6ba68488404e85acdd22a3030d0f5e56a108d4b27d744f18ceb50861b4'),
    'Linux': ('minio.linux-amd64.' + RELEASE,
              '7c5bd8512c6e966455b1d198209358b2d191c77a83ab377c4073281065fb855f'),
}


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--office-image', help='可选：受审查的 Office image@sha256，额外运行真实隔离转换')
    options = parser.parse_args()
    if options.office_image:
        from office_preview_runner import IMAGE
        if not IMAGE.fullmatch(options.office_image):
            parser.error('Office 转换镜像必须是固定仓库摘要')
    if platform.machine().lower() not in ('amd64', 'x86_64'):
        raise RuntimeError('该验收程序固定使用官方 amd64 发布产物')
    name, checksum = ASSETS[platform.system()]
    cache = ROOT / '.codex-validation' / 'storage-runtime'
    cache.mkdir(parents=True, exist_ok=True)
    binary = cache / name
    if not binary.exists() or hashlib.sha256(binary.read_bytes()).hexdigest() != checksum:
        url = f'https://github.com/minio/minio/releases/download/{RELEASE}/{name}'
        partial = binary.with_suffix(binary.suffix + '.partial')
        curl = shutil.which('curl.exe' if os.name == 'nt' else 'curl')
        if curl:
            subprocess.run([curl, '--fail', '--location', '--silent', '--show-error',
                            '--retry', '3', '--max-time', '240', '--output', str(partial), url],
                           check=True, timeout=300)
        else:
            with urllib.request.urlopen(url, timeout=60) as source, partial.open('wb') as target:
                shutil.copyfileobj(source, target)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != checksum:
            raise RuntimeError('官方 MinIO 下载 SHA-256 不匹配，保留 partial 并拒绝执行')
        partial.replace(binary)
    if hashlib.sha256(binary.read_bytes()).hexdigest() != checksum:
        raise RuntimeError('官方 MinIO 程序 SHA-256 不匹配，拒绝执行')
    if os.name != 'nt':
        binary.chmod(0o700)
    fixture = ROOT / '.codex-validation' / ('admincore-storage-' + secrets.token_hex(4))
    fixture.mkdir()
    port, console = free_port(), free_port()
    while console == port:
        console = free_port()
    environment = {**os.environ, 'MINIO_ROOT_USER': 'fixture-' + secrets.token_hex(8),
                   'MINIO_ROOT_PASSWORD': secrets.token_urlsafe(36), 'MINIO_BROWSER': 'off'}
    report = {'release': RELEASE, 'sha256': checksum, 'passed': False, 'ports': [port, console]}
    process = None
    try:
        with (fixture / 'minio.log').open('wb') as log:
            process = subprocess.Popen([str(binary), 'server', str(fixture / 'data'),
                                        '--address', f'127.0.0.1:{port}',
                                        '--console-address', f'127.0.0.1:{console}'],
                                       env=environment, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            report['pid'] = process.pid
            endpoint = f'http://127.0.0.1:{port}'
            for attempt in range(100):
                if process.poll() is not None:
                    raise RuntimeError('MinIO 提前退出，详见隔离日志')
                try:
                    with urllib.request.urlopen(endpoint + '/minio/health/ready', timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError('MinIO 启动超时')
            test_env = {**environment, 'DJANGO_ENV': 'testing',
                        'STORAGE_CONTRACT_ENDPOINT': endpoint,
                        'STORAGE_CONTRACT_ACCESS': environment['MINIO_ROOT_USER'],
                        'STORAGE_CONTRACT_SECRET': environment['MINIO_ROOT_PASSWORD']}
            tests = ['integration/test_s3_storage.py']
            if options.office_image:
                test_env['OFFICE_CONTRACT_IMAGE'] = options.office_image
                tests.append('integration/test_s3_office_preview.py')
            with (fixture / 'contract.log').open('wb') as output:
                result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'pytest', *tests,
                                         '-q', '--junitxml', str(fixture / 'junit.xml')],
                                        cwd=ROOT / 'backend', env=test_env, stdout=output,
                                        stderr=subprocess.STDOUT, timeout=600 if options.office_image else 180)
            report['passed'] = result.returncode == 0
            if not report['passed']:
                raise RuntimeError('S3 实测失败，详见隔离 contract.log')
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            report['stopped_pid'] = process.pid
        (fixture / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if report['passed']:
            data = (fixture / 'data').resolve()
            if data.parent == fixture.resolve():
                shutil.rmtree(data)
        print(json.dumps({'evidence': str(fixture), **report}, ensure_ascii=False))
    if not report['passed']:
        raise RuntimeError('存储验收未通过')


if __name__ == '__main__':
    main()
