"""离线检查仓库文档、链接、命令、模块定位和发布版本；不读取 .env。"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CURRENT = (
    'AGENTS.md', 'CLAUDE.md', 'README.md', '项目结构说明.md', 'VERSION.md', '快速参考.md',
    'docs/快速开始.md', 'docs/后端开发指南.md', 'docs/前端开发指南.md',
    'docs/API规范.md', 'docs/模块与基础能力.md', 'docs/发布与版本策略.md',
    'docs/底座版本与项目升级.md', 'docs/文档维护与文件保留策略.md',
)
LINK = re.compile(r'\[[^\]\n]*\]\((<[^>]+>|[^\n)]*?)(?:\s+"[^"]*")?\)')


def documentation_files(root):
    """维护仓库只取跟踪文档；无 Git 的导出项目覆盖其文档树。"""
    files = {root / name for name in CURRENT}
    if (root / '.git').exists():
        result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '*.md'],
                                capture_output=True, check=True, timeout=30)
        files.update(root / name for name in result.stdout.decode('utf-8').split('\0') if name)
    else:
        files.update(root.glob('*.md'))
        for directory in ('docs', 'design-spec', 'frontend/docs', 'frontend/third-party'):
            files.update((root / directory).rglob('*.md'))
        if (root / 'frontend/e2e/README.md').exists():
            files.add(root / 'frontend/e2e/README.md')
    files.update((root / 'docs/ai').glob('*.md'))
    return sorted(files)


def heading_ids(content):
    """当前文档使用 ATX 标题；保留中文，按 GitHub 规则处理同名锚点。"""
    result, seen = set(), {}
    # 示例代码中的标题不构成渲染后的章节。
    lines, fence = [], None
    for line in content.splitlines():
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
        else:
            lines.append(line)
    for title in re.findall(r'^ {0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$', '\n'.join(lines), re.M):
        title = re.sub(r'<[^>]*>', '', title).replace('`', '').lower()
        slug = re.sub(r'[^\w\-\s]', '', title).replace(' ', '-')
        number = seen.get(slug, 0)
        seen[slug] = number + 1
        result.add(f'{slug}-{number}' if number else slug)
    return result


def check(root=ROOT):
    root = Path(root).resolve()
    files = documentation_files(root)
    errors = []
    links = 0
    scripts = json.loads((root / 'frontend/package.json').read_text(encoding='utf-8'))['scripts']
    for path in files:
        if not path.is_file():
            errors.append(f'缺少文档：{path.relative_to(root)}')
            continue
        content = path.read_text(encoding='utf-8')
        for match in LINK.finditer(content):
            target = match[1].strip().strip('<>')
            parsed = urlsplit(target)
            local = not parsed.scheme or parsed.scheme == 'file' or (len(parsed.scheme) == 1 and target[1:2] == ':')
            if local and '.codex-validation' in unquote(parsed.path).replace('\\', '/').split('/'):
                errors.append(f'{path.relative_to(root)}：私有验收证据应使用文字路径，不能作为仓库附件链接 {target}')
                continue
            if local and parsed.scheme:
                errors.append(f'{path.relative_to(root)}：本地附件必须使用仓库相对路径 {target}')
                continue
            if parsed.scheme:
                continue
            links += 1
            destination = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if not destination.is_relative_to(root) or not destination.exists():
                errors.append(f'{path.relative_to(root)}：无效本地链接 {target}')
            elif parsed.fragment and destination.suffix == '.md':
                if unquote(parsed.fragment) not in heading_ids(destination.read_text(encoding='utf-8')):
                    errors.append(f'{path.relative_to(root)}：无效章节 {target}')
        for command in re.findall(r'\bnpm run ([\w:-]+)', content):
            if command not in scripts:
                errors.append(f'{path.relative_to(root)}：未定义 npm 命令 {command}')
        for script in re.findall(r'\b(?:python|python3|python\.exe)\s+((?:\.\./)?scripts/[\w./-]+\.py)', content):
            if not (root / script.removeprefix('../')).is_file():
                errors.append(f'{path.relative_to(root)}：脚本不存在 {script}')
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
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
