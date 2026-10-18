"""通过真实 Git CLI、Django 迁移及持久业务数据库验证升级验收脚本。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate_project_upgrades import validate  # noqa: E402


def test_real_django_continuous_upgrades_preserve_business_and_gate_baseline(tmp_path):
    output = tmp_path / 'evidence'
    report = validate(output)
    assert report['passed'] and report['temporary_removed']
    assert report['failed_gate_preserved_baseline'] and report['services_started'] == 0
    assert len(report['rounds']) == 2
    assert report['rounds'][0]['to_revision'] == report['rounds'][1]['from_revision']
    assert report['initial_data']['business_fingerprint'] == report['rounds'][0]['business_fingerprint'] == report['rounds'][1]['business_fingerprint']
    assert len(report['rounds'][0]['foundation_migrations']) == 2
    assert len(report['rounds'][1]['foundation_migrations']) == 3
    assert 'Applying foundation.0002_release... OK' in (output / 'round-1-validation.log').read_text(encoding='utf-8')
    assert 'Applying foundation.0003_revision... OK' in (output / 'round-2-validation.log').read_text(encoding='utf-8')
