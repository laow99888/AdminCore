"""真实 SSE 持续连接基线；调用方提供隔离会话、SQL/cgroup 观测，不记录凭据。"""
from concurrent.futures import ThreadPoolExecutor
import base64
import json
from pathlib import Path
import threading
import time

import requests


def valid_snapshot(value):
    if set(value) != {'request_id', 'topics'}:
        return False
    topics = value['topics']
    return (set(topics) == {'notifications', 'approvals', 'tasks'}
            and topics['notifications']['total'] == topics['notifications']['unread_count'] == 1
            and topics['approvals']['total'] == topics['approvals']['todo_count'] == 1
            and topics['tasks']['total'] == topics['tasks']['active_count'] == 1
            and len(topics['tasks']['active']) == 1 and topics['tasks']['active'][0]['progress'] == 37
            and 'PRIVATE_' not in json.dumps(value))


def expires(token):
    payload = token.split('.')[1]
    return json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))['exp']


def healthy(before, after):
    return (after['running'] and not after['oom_killed']
            and after['restart_count'] == before['restart_count']
            and after['memory_events']['oom'] == before['memory_events']['oom']
            and after['memory_events']['oom_kill'] == before['memory_events']['oom_kill'])


def measure(base, actors, observe, destination, *, seconds, overflow=None, arrival_seconds=0):
    """每个 actor 是独立用户/设备的真实 access/refresh；短流自然结束后重新建立。"""
    report = {'passed': False, 'connections': len(actors), 'requested_seconds': seconds,
              'arrival_seconds': arrival_seconds,
              'scope': '隔离 PostgreSQL/Nginx/单进程 ASGI，非生产 SLA；客户端含 HTTP/解码耗时',
              'samples': [], 'actors': [], 'health_ms': []}
    destination = Path(destination)
    stop = threading.Event()
    admitted = [threading.Event() for _ in actors]
    stats = [{'cycles': 0, 'snapshots': 0, 'heartbeats': 0, 'refreshes': 0,
              'admission_retries': 0, 'errors': [], 'max_reconnect_ms': 0} for _ in actors]
    report['actors'] = stats

    def persist():
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    def client(index):
        pair, row = dict(actors[index]), stats[index]
        disconnected_at = time.monotonic()
        try:
            while not stop.is_set():
                if expires(pair['access']) - time.time() < 60:
                    with requests.post(base + 'auth/refresh/', json={'refresh': pair['refresh']}, timeout=(5, 15)) as response:
                        if response.status_code != 200:
                            raise ValueError('refresh_status')
                        pair = response.json()['data']
                        if not pair.get('access') or not pair.get('refresh'):
                            raise ValueError('refresh_pair')
                        row['refreshes'] += 1
                with requests.get(base + 'realtime/events/', headers={'Authorization': 'Bearer ' + pair['access']},
                                  stream=True, timeout=(5, 10)) as response:
                    if response.status_code == 429 and time.monotonic() - disconnected_at < 5:
                        row['admission_retries'] += 1
                        stop.wait(.25)
                        continue
                    if response.status_code != 200 or response.headers.get('Cache-Control') != 'private, no-store':
                        raise ValueError('stream_http_' + str(response.status_code))
                    event, data, received = '', [], False
                    for line in response.iter_lines(chunk_size=1, decode_unicode=True):
                        if stop.is_set():
                            break
                        if line.startswith(': heartbeat'):
                            row['heartbeats'] += 1
                        elif line.startswith('event:'):
                            event = line[6:].strip()
                        elif line.startswith('data:'):
                            data.append(line[5:].strip())
                        elif not line and data:
                            value = json.loads('\n'.join(data))
                            if event != 'snapshot' or not valid_snapshot(value) or pair['access'] in json.dumps(value):
                                raise ValueError('unexpected_frame')
                            row['snapshots'] += 1
                            row['max_reconnect_ms'] = max(row['max_reconnect_ms'],
                                round((time.monotonic() - disconnected_at) * 1000, 2))
                            received = True
                            admitted[index].set()
                            event, data = '', []
                    if not received and not stop.is_set():
                        raise ValueError('empty_stream')
                    if not stop.is_set():
                        row['cycles'] += 1
                disconnected_at = time.monotonic()
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            # 只保存异常类别；请求异常的完整内容可能含凭据或私有响应。
            safe = {'refresh_status', 'refresh_pair', 'unexpected_frame', 'empty_stream'}
            detail = str(error)
            row['errors'].append(detail if detail in safe or detail in {
                'stream_http_' + str(code) for code in [200, 400, 401, 403, 404, 429, 500, 502, 503, 504]
            } else type(error).__name__)
            stop.set()

    try:
        report['before'] = observe()
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=len(actors)) as pool:
            futures = []
            for index in range(len(actors)):
                futures.append(pool.submit(client, index))
                if stop.wait(arrival_seconds):
                    break
            try:
                deadline = time.monotonic() + 20
                while not all(event.is_set() for event in admitted) and not stop.is_set() and time.monotonic() < deadline:
                    stop.wait(.1)
                report['all_admitted'] = all(event.is_set() for event in admitted)
                report['admitted_sample'] = observe()
                if not report['all_admitted'] or report['admitted_sample']['active_leases'] != len(actors):
                    stop.set()
                if overflow and not stop.is_set():
                    with requests.get(base + 'realtime/events/', headers={'Authorization': 'Bearer ' + overflow['access']},
                                      stream=True, timeout=(5, 10)) as response:
                        report['overflow_status'] = response.status_code
                    if report['overflow_status'] != 429:
                        stop.set()
                deadline = time.monotonic() + seconds
                while not stop.is_set() and time.monotonic() < deadline:
                    tick = time.perf_counter()
                    with requests.get(base + 'health/', timeout=(3, 3)) as response:
                        if response.status_code != 200:
                            raise ValueError('health_status')
                    report['health_ms'].append(round((time.perf_counter() - tick) * 1000, 2))
                    sample = observe()
                    report['samples'].append(sample)
                    persist()
                    if not healthy(report['before'], sample):
                        stop.set()
                    stop.wait(min(10, max(0, deadline - time.monotonic())))
            finally:
                stop.set()
                for future in futures:
                    future.result(timeout=15)
        report['elapsed_seconds'] = round(time.monotonic() - started, 2)
        # 实际断开应立即回收；允许 HTTP 读超时/DB 调度的十秒观察窗。
        deadline = time.monotonic() + 10
        while True:
            report['after'] = observe()
            if report['after']['total_leases'] == report['before']['total_leases'] or time.monotonic() >= deadline:
                break
            time.sleep(.25)
        minimum_cycles = max(1, seconds // 25 - 2)
        report['passed'] = (report.get('all_admitted', False)
            and report['admitted_sample']['active_leases'] == len(actors)
            and (not overflow or report.get('overflow_status') == 429)
            and report['elapsed_seconds'] >= seconds
            and all(not row['errors'] and row['cycles'] >= minimum_cycles and row['snapshots'] > 0
                    and row['heartbeats'] >= minimum_cycles * 3 and row['max_reconnect_ms'] < 10000
                    and (seconds < 300 or row['refreshes'] >= 1) for row in stats)
            and bool(report['health_ms']) and max(report['health_ms']) < 3000
            and report['after']['active_leases'] == 0
            and report['after']['total_leases'] == report['before']['total_leases']
            and healthy(report['before'], report['after']))
        return report
    finally:
        persist()
