"""容量证据不能把错误响应、伪图片或 OOM/重启当成成功。"""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

spec = importlib.util.spec_from_file_location('image_capacity', Path(__file__).parents[1] / 'image_capacity.py')
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)


@pytest.mark.parametrize('failure', [None, 'http', 'image', 'oom', 'restart'])
def test_real_decoding_and_resource_failures_control_result(monkeypatch, tmp_path, failure):
    output = io.BytesIO()
    with Image.new('RGB', (2000, 2000), 'blue') as image:
        image.save(output, 'WEBP')
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=503 if failure == 'http' else 200,
                               content=b'not an image' if failure == 'image' else output.getvalue(),
                               headers={'Cache-Control': 'private, no-store'})

    monkeypatch.setattr(capacity.requests, 'post', post)
    observations = []

    def snapshot():
        after_load = len(calls) > 0
        result = {'memory_events': {'oom_kill': int(after_load and failure == 'oom'), 'oom': 0},
                  'restart_count': int(after_load and failure == 'restart'), 'running': True, 'oom_killed': False}
        observations.append(result)
        return result

    destination = tmp_path / 'capacity.json'
    report = capacity.measure('http://fixture/api/v1/', [('private-fixture-token', 'own-file')] * 4, snapshot, destination)
    assert report['passed'] is (failure is None)
    assert len(calls) == (48 if failure is None else 12)
    assert len(report['stages']) == (4 if failure is None else 1)
    assert json.loads(destination.read_text(encoding='utf-8')) == report
    assert 'private-fixture-token' not in destination.read_text(encoding='utf-8')
    if failure == 'image':
        assert all(stage['statuses'] == {'200': 12} and stage['valid_images'] == 0 for stage in report['stages'])
