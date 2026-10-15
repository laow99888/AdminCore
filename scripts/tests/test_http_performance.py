"""负载门槛反例：慢接口、错误响应、缺失样本必须使验收失败。"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location('performance', Path(__file__).parents[1] / 'validate_http_performance.py')
performance = module_from_spec(spec)
spec.loader.exec_module(performance)


def samples():
    return [{'scenario': name, 'ok': True, 'milliseconds': 20 + index}
            for name in performance.SCENARIOS for index in range(20)]


def test_gate_reports_nearest_rank_per_scenario():
    result = performance.evaluate(samples(), 8)
    assert result['requests'] == 160
    assert all(row['p95_ms'] == 38 and row['p99_ms'] == 39 for row in result['scenarios'].values())


@pytest.mark.parametrize('problem', ['slow_p95', 'slow_p99', 'error', 'missing'])
def test_gate_rejects_regressions(problem):
    rows = samples()
    if problem == 'slow_p95':
        for row in rows[:2]:
            row['milliseconds'] = performance.P95_MS + 1
    elif problem == 'slow_p99':
        rows[0]['milliseconds'] = performance.P99_MS + 1
    elif problem == 'error':
        rows[0]['ok'] = False
    else:
        rows.pop()
    with pytest.raises(AssertionError):
        performance.evaluate(rows, 8)
