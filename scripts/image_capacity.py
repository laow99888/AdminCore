"""隔离图片 HTTP 容量基线；调用方创建测试账号/原件并提供 cgroup 观测。"""
from concurrent.futures import ThreadPoolExecutor
import io
import json
import math
from pathlib import Path
import time

import requests
from PIL import Image


def measure(base, actors, resource_snapshot, destination, *, runtime='1进程4线程'):
    report = {'passed': False, 'source_pixels': 16_000_000, 'source_size': [4000, 4000],
              'output_size': [2000, 2000], 'output_format': 'webp', 'quality': 80, 'stages': [],
              'timing': 'POST开始至响应读完并完成客户端图片解码校验；不等同于服务端处理耗时',
              'percentile': '每阶段12个样本，nearest-rank p95等于该阶段最大值，仅作小样本基线',
              'scope': '单容器1 CPU/1536 MiB，' + runtime + '；合成JPEG，不代表生产容量'}
    destination = Path(destination)

    def healthy(before, after):
        return (after['memory_events']['oom_kill'] == before['memory_events']['oom_kill']
                and after['memory_events']['oom'] == before['memory_events']['oom']
                and after['restart_count'] == before['restart_count']
                and after['running'] and not after['oom_killed'])

    def request(index, *, same_actor):
        token, identifier = actors[0 if same_actor else index % len(actors)]
        started = time.perf_counter()
        try:
            response = requests.post(base + 'files/' + identifier + '/transform/',
                headers={'Authorization': 'Bearer ' + token}, json={
                    'lifecycle_version': 1, 'width': 2000, 'height': 2000, 'format': 'webp', 'quality': 80}, timeout=(5, 20))
            valid = False
            if response.status_code == 200:
                try:
                    with Image.open(io.BytesIO(response.content)) as image:
                        image.load()
                        valid = image.size == (2000, 2000) and image.format == 'WEBP'
                except (OSError, ValueError):
                    pass
                valid = valid and response.headers.get('Cache-Control') == 'private, no-store'
            return {'status': response.status_code, 'valid': valid,
                    'latency_ms': round((time.perf_counter() - started) * 1000, 2)}
        except requests.RequestException:
            # 不输出 Authorization、原始响应或异常中可能包含的请求详情。
            return {'status': 0, 'valid': False,
                    'latency_ms': round((time.perf_counter() - started) * 1000, 2)}

    try:
        report['before'] = resource_snapshot()
        for concurrency, same_actor in [(1, False), (2, False), (4, False), (4, True)]:
            before = resource_snapshot()
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                results = list(pool.map(lambda index: request(index, same_actor=same_actor), range(12)))
            seconds = time.perf_counter() - started
            latencies = sorted(row['latency_ms'] for row in results)
            after = resource_snapshot()
            stage = {'concurrency': concurrency, 'same_actor_and_file': same_actor, 'requests': len(results),
                     'elapsed_seconds': round(seconds, 3), 'requests_per_second': round(len(results) / seconds, 3),
                     'p50_ms': latencies[math.ceil(len(latencies) * .50) - 1],
                     'p95_ms': latencies[math.ceil(len(latencies) * .95) - 1], 'max_ms': max(latencies),
                     'statuses': {str(status): sum(row['status'] == status for row in results)
                                  for status in sorted({row['status'] for row in results})},
                     'valid_images': sum(row['valid'] for row in results), 'before': before, 'after': after}
            report['stages'].append(stage)
            # 每一阶段落盘，即使后续观察或进程失败，也保留已取得的基线。
            destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            if stage['valid_images'] != stage['requests'] or not healthy(report['before'], after):
                report['after'] = after
                report['aborted_after_stage'] = len(report['stages'])
                return report
        report['after'] = resource_snapshot()
        report['passed'] = (all(stage['valid_images'] == stage['requests'] for stage in report['stages'])
                            and healthy(report['before'], report['after']))
        return report
    finally:
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
