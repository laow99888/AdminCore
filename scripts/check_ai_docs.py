"""离线检查现行 AI 导航、本地链接、模块定位和发布版本；不读取 .env。"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CURRENT = (
    'AGENTS.md', 'CLAUDE.md', 'README.md', '项目结构说明.md', 'VERSION.md', '快速参考.md',
    'docs/快速开始.md', 'docs/后端开发指南.md', 'docs/前端开发指南.md',
    'docs/API规范.md', 'docs/模块与基础能力.md', 'docs/发布与版本策略.md',
    'docs/底座版本与项目升级.md', 'docs/文档维护与文件保留策略.md',
)
LINK = re.compile(r'\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\)')


def check(root=ROOT):
    root = Path(root).resolve()
    files = [root / name for name in CURRENT]
    files.extend(sorted((root / 'docs/ai').glob('*.md')))
    errors = []
    links = 0
    for path in files:
        if not path.is_file():
            errors.append(f'缺少文档：{path.relative_to(root)}')
            continue
        content = path.read_text(encoding='utf-8')
        for match in LINK.finditer(content):
            target = match[1].strip('<>')
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith('#'):
                continue
            links += 1
            destination = (path.parent / unquote(parsed.path)).resolve()
            if not destination.is_relative_to(root) or not destination.exists():
                errors.append(f'{path.relative_to(root)}：无效本地链接 {target}')
    navigation = root / 'docs/ai/能力地图.md'
    registry = root / 'backend/apps/core/modules.py'
    if navigation.is_file() and registry.is_file():
        mapping = navigation.read_text(encoding='utf-8')
        tree = ast.parse(registry.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if (isinstance(node, ast.ImportFrom) and node.module
                    and node.module.startswith('apps.')
                    and any(alias.name == 'MODULE' for alias in node.names)):
                app = node.module.split('.')[1]
                if f'../../backend/apps/{app}/' not in mapping:
                    errors.append(f'能力地图缺少已注册模块入口：{app}')
    try:
        version = json.loads((root / 'backend/config/base-version.json').read_text(encoding='utf-8'))['version']
        schema = json.loads((root / 'frontend/src/api/generated/openapi.json').read_text(encoding='utf-8'))
        if schema['info']['version'] != version:
            errors.append('产品版本与 OpenAPI 不一致，请重新生成 SDK')
        changelog = (root / 'CHANGELOG.md').read_text(encoding='utf-8')
        if not re.search(r'^## ' + re.escape(version) + r'(?:\s|$)', changelog, re.M):
            errors.append('CHANGELOG 缺少当前产品版本')
    except (OSError, KeyError, ValueError) as exc:
        errors.append(f'版本来源无效：{type(exc).__name__}')
    if errors:
        raise ValueError('\n'.join(errors))
    return {'documents': len(files), 'local_links': links, 'version': version}


if __name__ == '__main__':
    try:
        print(json.dumps(check(), ensure_ascii=False))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
