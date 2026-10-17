"""用本地真实 HTTP 流验证验收器拒绝异常；不冒充产品 ASGI 容量测试。"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import importlib.util
import json
from pathlib import Path
import threading
import time

import pytest

spec = importlib.util.spec_from_file_location('realtime_capacity', Path(__file__).parents[1] / 'realtime_capacity.py')
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)


def snapshot():
    return {'request_id': 'fixture', 'topics': {
        'notifications': {'total': 1, 'unread_count': 1},
        'approvals': {'total': 1, 'todo_count': 1},
        'tasks': {'total': 1, 'active_count': 1, 'active': [{'progress': 37}]}}}


@contextmanager
def peer(failure):
    active = 0
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert self.path.endswith('/auth/refresh/') and data == {'refresh': 'private-refresh'}
            payload = base64.urlsafe_b64encode(json.dumps({'exp': time.time() + 600}).encode()).decode().rstrip('=')
            value = {'data': {'access': 'private.' + payload + '.fixture', 'refresh': 'rotated-private'}}
            if failure == 'refresh_pair':
                del value['data']['refresh']
            self.send_response(503 if failure == 'refresh_http' else 200)
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        def do_GET(self):
            nonlocal active
            if self.path.endswith('/health/'):
                self.send_response(200)
                self.end_headers()
                return
            if self.headers.get('Authorization') == 'Bearer overflow':
                self.send_response(200 if failure == 'overflow' else 429)
                self.end_headers()
                return
            self.send_response(503 if failure == 'http' else 200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'private, no-store')
            self.end_headers()
            with lock:
                active += 1
            try:
                value = snapshot()
                if failure == 'frame':
                    value['topics']['tasks']['total'] = 2
                event = 'access_revoked' if failure == 'revoked' else 'snapshot'
                self.wfile.write(('event: ' + event + '\ndata: ' + json.dumps(value)
                                  + '\n\n' + ': heartbeat\n\n' * 3).encode())
                self.wfile.flush()
                time.sleep(.4)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with lock:
                    active -= 1

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def observe():
        with lock:
            count = active
        return {'active_leases': count, 'total_leases': count, 'running': True, 'oom_killed': False,
                'restart_count': int(failure == 'restart' and count > 0),
                'memory_events': {'oom': 0, 'oom_kill': int(failure == 'oom' and count > 0)}}

    try:
        yield f'http://127.0.0.1:{server.server_port}/api/v1/', observe
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize('failure', [None, 'refresh', 'refresh_http', 'refresh_pair',
                                     'http', 'frame', 'revoked', 'overflow', 'oom', 'restart'])
def test_real_http_stream_and_failure_evidence(tmp_path, failure):
    payload = base64.urlsafe_b64encode(json.dumps({'exp': time.time() + (10 if failure and failure.startswith('refresh') else 600)}).encode()).decode().rstrip('=')
    token = 'private.' + payload + '.fixture'
    destination = tmp_path / 'report.json'
    with peer(failure) as (base, observe):
        report = capacity.measure(base, [{'access': token, 'refresh': 'private-refresh'}], observe,
                                  destination, seconds=.8, overflow={'access': 'overflow'})
    assert report['passed'] is (failure in (None, 'refresh'))
    if failure == 'refresh':
        assert report['actors'][0]['refreshes'] == 1
    assert json.loads(destination.read_text(encoding='utf-8')) == report
    assert token not in destination.read_text(encoding='utf-8')
    assert 'private-refresh' not in destination.read_text(encoding='utf-8')
    assert 'rotated-private' not in destination.read_text(encoding='utf-8')


def test_snapshot_rejects_cross_scope_counts_private_data_and_unexpected_shape():
    value = snapshot()
    assert capacity.valid_snapshot(value)
    value['topics']['notifications']['total'] = 2
    assert not capacity.valid_snapshot(value)
    value = snapshot()
    value['request_id'] = 'PRIVATE_BODY'
    assert not capacity.valid_snapshot(value)
    value = snapshot()
    value['access'] = 'secret'
    assert not capacity.valid_snapshot(value)
