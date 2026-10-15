from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import shutil

import pytest

SPEC = spec_from_file_location('dependency_locks', Path(__file__).parents[1] / 'check_dependency_locks.py')
module = module_from_spec(SPEC)
SPEC.loader.exec_module(module)


@pytest.fixture
def copied(tmp_path):
    for name in ['backend/requirements.txt', 'backend/requirements.lock', 'backend/requirements.minimal.txt', 'backend/requirements.minimal.lock', 'backend/Dockerfile',
                 'frontend/package.json', 'frontend/package-lock.json', 'frontend/.npmrc', 'frontend/Dockerfile',
                 'frontend/vendor/xlsx-0.20.3.tgz', '.python-version', '.nvmrc']:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(module.ROOT / name, target)
    return tmp_path


def mutate(root, path, callback):
    target = root / path
    content = json.loads(target.read_text(encoding='utf-8'))
    callback(content)
    target.write_text(json.dumps(content), encoding='utf-8')


def test_real_project_locks():
    assert module.check()['passed']


@pytest.mark.parametrize('line', ['Django>=5.2', 'https://example.test/pkg.whl', '-r secrets.txt', 'Django==5.2.0rc1'])
def test_reject_unfixed_or_executable_requirements(line):
    with pytest.raises(ValueError):
        module.python_pins(line)


@pytest.mark.parametrize('line', ['Django==5.2.18', 'Django==5.2.18 --hash=sha256:bad'])
def test_reject_missing_or_invalid_hash(line):
    with pytest.raises(ValueError):
        module.python_pins(line, hashed=True)


def test_direct_python_drift(copied):
    target = copied / 'backend/requirements.txt'
    target.write_text(target.read_text(encoding='utf-8').replace('Django==5.2.18', 'Django==5.2.19'), encoding='utf-8')
    with pytest.raises(ValueError, match='哈希锁不一致'):
        module.check(copied)


def test_npm_manifest_drift(copied):
    mutate(copied, 'frontend/package.json', lambda data: data['dependencies'].update(vue='3.5.44'))
    with pytest.raises(ValueError, match='根声明不一致'):
        module.check(copied)


def test_npm_resolved_drift(copied):
    mutate(copied, 'frontend/package-lock.json', lambda data: data['packages']['node_modules/vue'].update(version='3.5.44'))
    with pytest.raises(ValueError, match='稳定精确版本'):
        module.check(copied)


def test_vendor_tampering(copied):
    target = copied / 'frontend/vendor/xlsx-0.20.3.tgz'
    target.write_bytes(target.read_bytes() + b'tamper')
    with pytest.raises(ValueError, match='摘要'):
        module.check(copied)


def test_runtime_drift(copied):
    (copied / '.nvmrc').write_text('24.22.0', encoding='utf-8')
    with pytest.raises(ValueError, match='Node运行时'):
        module.check(copied)


def test_minimal_direct_drift(copied):
    target = copied / 'backend/requirements.minimal.txt'
    target.write_text(target.read_text(encoding='utf-8').replace('Django==5.2.18', 'Django==5.2.19'), encoding='utf-8')
    with pytest.raises(ValueError, match='完整清单同版本'):
        module.check(copied)


def test_minimal_lock_drift(copied):
    target = copied / 'backend/requirements.minimal.lock'
    target.write_text(target.read_text(encoding='utf-8').replace('django==5.2.18', 'django==5.2.19'), encoding='utf-8')
    with pytest.raises(ValueError, match='精简直接依赖与哈希锁不一致'):
        module.check(copied)


def test_minimal_rejects_heavy_packages(copied):
    target = copied / 'backend/requirements.minimal.lock'
    target.write_text(target.read_text(encoding='utf-8') + '\nnh3==0.3.3 --hash=sha256:' + '0' * 64 + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match='精简哈希锁'):
        module.check(copied)


def test_minimal_lock_uses_only_reviewed_hashes(copied):
    target = copied / 'backend/requirements.minimal.lock'
    content = target.read_text(encoding='utf-8')
    target.write_text(module.re.sub(r'sha256:[0-9a-f]{64}', 'sha256:' + '0' * 64, content, count=1), encoding='utf-8')
    with pytest.raises(ValueError, match='已审核的包摘要'):
        module.check(copied)
