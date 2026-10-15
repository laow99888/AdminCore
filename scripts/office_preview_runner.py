"""宿主 Office 队列执行器；固定管理命令和逐作业容器，不挂载 Docker socket。"""
import argparse
import base64
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 10 * 1024 * 1024
FORMATS = {'docx', 'xlsx', 'pptx', 'odt', 'ods', 'odp'}
IMAGE = re.compile(r'[a-z0-9][a-z0-9./:_-]{0,180}@sha256:[a-f0-9]{64}')


class CleanupFailure(RuntimeError):
    def __init__(self, container):
        self.resources = [container] if isinstance(container, str) else list(container)
        self.container = ','.join(self.resources)
        super().__init__('owned_resource_cleanup_unconfirmed: ' + self.container)


def protocol(action, payload=None):
    if (ROOT / 'admincore.project.json').is_file():
        from create_project import compose_command, verify_ownership
        verify_ownership(ROOT)
        prefix = compose_command(ROOT, 'status')[:-1]
    else:
        prefix = ['docker', 'compose']
    result = subprocess.run(prefix + ['exec', '-T', 'backend', 'python', 'manage.py',
        'office_queue', action], cwd=ROOT, input=json.dumps(payload).encode() if payload else None,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=35, check=True)
    if len(result.stdout) > 14 * 1024 * 1024:
        raise ValueError('invalid_protocol')
    return json.loads(result.stdout)


def container_args(name, source, image):
    if not IMAGE.fullmatch(image) or not re.fullmatch(r'admincore-office-[a-f0-9]{32}', name):
        raise ValueError('invalid_container_identity')
    source = Path(source)
    if source.is_symlink():
        raise ValueError('invalid_source')
    source = source.resolve(strict=True)
    if not source.is_file() or source.suffix[1:] not in FORMATS or ',' in str(source):
        raise ValueError('invalid_source')
    return ['docker', 'create', '--name', name, '--label', 'admincore.office-preview=1',
        '--network', 'none', '--user', '65532:65532', '--read-only', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges:true', '--memory', '768m', '--memory-swap', '768m',
        '--cpus', '1', '--pids-limit', '96', '--ulimit', 'nofile=128:128',
        '--ulimit', 'fsize=12582912:12582912', '--init', '--log-driver', 'none',
        '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=134217728,uid=65532,gid=65532,mode=700',
        '--mount', 'type=volume,source=' + name + '-input,target=/input,readonly',
        '--entrypoint', '/usr/bin/python3', image, '/opt/admincore/convert.py', source.suffix[1:]]


@contextmanager
def staged_source(name, source, image, *, command=subprocess.run):
    """Copy one file over the Docker API, including remote/WSL engines.

    The loader is never started. The converter sees only this job's read-only
    volume; no host directory or Docker socket is exposed to document parsers.
    """
    args = container_args(name, source, image)
    volume, loader = name + '-input', name + '-loader'
    resources = []
    unconfirmed = []
    try:
        resources.append(('volume', volume))
        command(['docker', 'volume', 'create', '--label', 'admincore.office-preview=1', volume],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        loader_args = args[:]
        loader_args[loader_args.index('--name') + 1] = loader
        loader_args[loader_args.index('--mount') + 1] = 'type=volume,source=' + volume + ',target=/input'
        loader_args[loader_args.index('--entrypoint') + 1:] = ['/usr/bin/true', image]
        resources.append(('container', loader))
        command(loader_args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        command(['docker', 'cp', str(Path(source).resolve()), loader + ':/input/source.' + Path(source).suffix[1:]],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        yield args
    except CleanupFailure as exc:
        unconfirmed.extend(exc.resources)
        raise
    finally:
        failures = unconfirmed[:]
        for kind, resource in reversed(resources):
            for attempt in range(2):
                try:
                    operation = ['docker', 'rm', '--force', resource] if kind == 'container' else ['docker', 'volume', 'rm', resource]
                    command(operation, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                    break
                except Exception:
                    if attempt == 1:
                        failures.append(resource)
        if failures:
            raise CleanupFailure(failures) from None


def convert(source, image, *, command=subprocess.run, popen=subprocess.Popen):
    name = 'admincore-office-' + uuid.uuid4().hex
    with staged_source(name, source, image, command=command) as args:
        return _convert(name, args, command=command, popen=popen)


def _convert(name, args, *, command, popen):
    process = None
    executor = None
    try:
        command(args, check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=20)
        process = popen(['docker', 'start', '--attach', name], stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL)
        executor = ThreadPoolExecutor(max_workers=1)
        started = time.monotonic()
        future = executor.submit(process.stdout.read, MAX_BYTES + 1)
        try:
            output = future.result(timeout=75)
        except FutureTimeout:
            raise TimeoutError('conversion_timeout') from None
        if len(output) > MAX_BYTES:
            raise ValueError('oversized_result')
        if process.wait(timeout=max(1, 75 - (time.monotonic() - started))) != 0:
            raise ValueError('conversion_failed')
        if not output.startswith(b'%PDF-'):
            raise ValueError('invalid_result')
        return output
    finally:
        # Only the random name created by this invocation is removable.
        cleanup_error = None
        try:
            for attempt in range(2):
                try:
                    command(['docker', 'rm', '--force', name], check=True, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=15)
                    cleanup_error = None
                    break
                except Exception as exc:
                    cleanup_error = exc
        finally:
            if process:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                process.stdout.close()
            if executor:
                executor.shutdown(wait=False, cancel_futures=True)
        if cleanup_error:
            # Stop taking jobs rather than silently accumulate unconfirmed containers.
            raise CleanupFailure(name) from None


def once(image):
    if not IMAGE.fullmatch(image):
        raise ValueError('required_pinned_image')
    job = protocol('claim')
    if job is None:
        return False
    identifier = str(uuid.UUID(job['job_id']))
    token = job['token']
    if (set(job) != {'job_id', 'token', 'extension', 'source', 'engine', 'source_sha256'}
            or job['engine'] != image or job['extension'] not in FORMATS
            or not re.fullmatch('[a-f0-9]{64}', token)):
        raise ValueError('invalid_claim')
    folder = Path(tempfile.mkdtemp(prefix='admincore-office-' + identifier + '-')).resolve()
    completed = False
    try:
        content = base64.b64decode(job['source'], validate=True)
        if not 0 < len(content) <= MAX_BYTES or hashlib.sha256(content).hexdigest() != job['source_sha256']:
            raise ValueError('source_checksum')
        source = folder / ('source.' + job['extension'])
        source.write_bytes(content)
        # The parent directory remains private (0700); the sandbox UID must read the
        # single bind-mounted file even when the host account uses umask 077.
        source.chmod(0o644)
        output = convert(source, image)
        protocol('finish', {'job_id': identifier, 'token': token, 'pdf': base64.b64encode(output).decode()})
        completed = True
    except Exception as exc:
        code = 'conversion_timeout' if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)) else 'conversion_failed'
        try:
            protocol('fail', {'job_id': identifier, 'token': token, 'code': code})
        except Exception:
            pass
        # No document bytes, original filename, token, command or raw exception in report.
        report = {'job_id': identifier, 'error': code}
        if isinstance(exc, CleanupFailure):
            report['cleanup_unconfirmed_resources'] = exc.resources
        (folder / 'failure.json').write_text(json.dumps(report), encoding='utf-8')
        print(json.dumps({**report, 'retained_fixture': str(folder)}), flush=True)
        if isinstance(exc, CleanupFailure):
            raise
    finally:
        source = folder / ('source.' + job['extension'])
        if source.is_file():
            source.unlink()
        if completed:
            if (folder.parent != Path(tempfile.gettempdir()).resolve()
                    or not folder.name.startswith('admincore-office-' + identifier + '-')):
                raise ValueError('unexpected_cleanup_target')
            shutil.rmtree(folder)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if not IMAGE.fullmatch(args.image):
        parser.error('镜像必须固定为受审查的 image@sha256:digest')
    while True:
        once(args.image)
        if args.once:
            return
        time.sleep(3)


if __name__ == '__main__':
    try:
        main()
    except CleanupFailure as exc:
        raise SystemExit(str(exc)) from None
