"""只读校验直接依赖、哈希锁和运行时来源；不联网、不安装或修改文件。"""
from pathlib import Path
import base64
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
PIN = re.compile(r'([A-Za-z0-9_.-]+)==([0-9][A-Za-z0-9_.+!-]*)(?:\s*;.*)?$')
EXACT = re.compile(r'\d+\.\d+\.\d+(?:\.\w+)*$')


def require(condition, label):
    if not condition:
        raise ValueError(label)


def normalized(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def python_pins(content, hashed=False):
    entries = {}
    logical = re.sub(r'\\\r?\n\s*', ' ', content)
    for line in logical.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        declaration, *hashes = line.split('--hash=')
        match = PIN.fullmatch(declaration.strip())
        require(match is not None, 'Python依赖必须精确固定且不能包含远程URL/安装指令')
        name, version = match.groups()
        require(not re.search(r'(?:a|b|rc|dev)\d', version, re.I), 'Python依赖不能使用预发布版本')
        if hashed:
            require(bool(hashes) and all(re.fullmatch(r'sha256:[0-9a-f]{64}', value.strip()) for value in hashes), '锁文件条目缺少有效SHA256')
        else:
            require(not hashes, '直接清单不得嵌入哈希锁条目')
        key = normalized(name)
        # 同一个包可能有不同平台标记，但不能悄悄锁到不同版本。
        require(key not in entries or entries[key] == version, '依赖重复且版本不一致')
        entries[key] = version
    require(bool(entries), '依赖清单不能为空')
    return entries


def check(root=ROOT):
    read = lambda path: (root / path).read_text(encoding='utf-8')
    direct = python_pins(read('backend/requirements.txt'))
    locked = python_pins(read('backend/requirements.lock'), hashed=True)
    require(all(locked.get(name) == version for name, version in direct.items()), 'Python直接依赖与哈希锁不一致，请重新生成requirements.lock')
    minimal_direct = python_pins(read('backend/requirements.minimal.txt'))
    minimal_locked = python_pins(read('backend/requirements.minimal.lock'), hashed=True)
    require(all(direct.get(name) == version for name, version in minimal_direct.items()), '精简直接依赖必须与完整清单同版本')
    require(all(minimal_locked.get(name) == version for name, version in minimal_direct.items()), '精简直接依赖与哈希锁不一致')
    require(all(locked.get(name) == version for name, version in minimal_locked.items()), '精简哈希锁必须是完整哈希锁的同版本子集')
    def hashes(content):
        result = {}
        for line in re.sub(r'\\\r?\n\s*', ' ', content).splitlines():
            declaration, *values = line.split('#', 1)[0].strip().split('--hash=')
            if declaration.strip():
                name = normalized(PIN.fullmatch(declaration.strip()).group(1))
                result.setdefault(name, set()).update(value.strip() for value in values)
        return result
    full_hashes = hashes(read('backend/requirements.lock'))
    require(all(values == full_hashes.get(name) for name, values in hashes(read('backend/requirements.minimal.lock')).items()), '精简依赖哈希必须复用完整锁已审核的包摘要')
    require(not {'pandas', 'numpy', 'openpyxl', 'pypdf', 'boto3', 'botocore', 'django-storages', 'nh3', 'authlib', 'joserfc', 'pytest', 'ipython', 'django-extensions'} & minimal_locked.keys(), '精简哈希锁不能包含可选重依赖或开发工具')
    package = json.loads(read('frontend/package.json'))
    lock = json.loads(read('frontend/package-lock.json'))
    require(lock.get('lockfileVersion') == 3, '前端锁文件必须为v3')
    for section in ['dependencies', 'devDependencies']:
        declarations = package.get(section, {})
        require(declarations == lock['packages'][''].get(section, {}), 'npm直接依赖与锁文件根声明不一致')
        for name, version in declarations.items():
            entry = lock['packages'].get('node_modules/' + name, {})
            if name == 'xlsx':
                require(version == 'file:vendor/xlsx-0.20.3.tgz', 'SheetJS必须使用已审核的本地官方包')
                archive = root / 'frontend' / version.removeprefix('file:')
                digest = base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode()
                require(entry.get('resolved') == version and entry.get('version') == '0.20.3' and entry.get('integrity') == 'sha512-' + digest, 'SheetJS摘要/版本/来源不一致')
            else:
                require(EXACT.fullmatch(version) is not None and entry.get('version') == version, 'npm直接依赖必须为稳定精确版本并与已解析锁一致')
                require(bool(re.fullmatch(r'sha512-[A-Za-z0-9+/]+={0,2}', entry.get('integrity', ''))), 'npm直接依赖缺少SHA512')
    python = read('.python-version').strip()
    node = read('.nvmrc').strip()
    require(f'FROM python:{python}-slim' in read('backend/Dockerfile'), 'Python运行时与Dockerfile漂移')
    require(package['engines']['node'] == node and f'FROM node:{node}-slim' in read('frontend/Dockerfile'), 'Node运行时与Dockerfile漂移')
    require(package['packageManager'] == 'npm@' + package['engines']['npm'], 'npm版本来源不一致')
    require(lock['packages']['']['engines'] == package['engines'], 'npm锁运行时声明不一致')
    require('engine-strict=true' in read('frontend/.npmrc') and 'save-exact=true' in read('frontend/.npmrc'), 'npm必须保持精确保存和引擎校验')
    require(package['dependencies']['@tiptap/pm'] == package['dependencies']['@tiptap/starter-kit'] == package['dependencies']['@tiptap/vue-3'], 'Tiptap依赖必须同步')
    require(package['devDependencies']['vitest'] == package['devDependencies']['@vitest/coverage-v8'], 'Vitest与覆盖率依赖必须同步')
    return {'passed': True, 'python_direct': len(direct), 'python_locked': len(locked), 'python_minimal_direct': len(minimal_direct), 'python_minimal_locked': len(minimal_locked), 'npm_direct': sum(len(package[key]) for key in ['dependencies', 'devDependencies']), 'network': False, 'files_modified': False}


if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False))
