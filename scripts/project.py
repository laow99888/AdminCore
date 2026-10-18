"""生成项目的固定运维和受控源码升级入口；不删除数据卷。"""
import argparse
import json
from pathlib import Path
import subprocess

from create_project import ProjectError, run_project, upgrade_plan
from project_upgrade import accept_upgrade, apply_upgrade, read_json, restore_upgrade


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['up', 'status', 'check', 'stop', 'upgrade-plan',
                                         'upgrade-apply', 'upgrade-accept', 'upgrade-restore'])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--output', type=Path, help='将只读升级计划写入新JSON文件')
    parser.add_argument('--plan', type=Path, help='已审阅的升级计划JSON')
    parser.add_argument('--keep-local', action='append', default=[], help='明确保留本地变更的路径')
    parser.add_argument('--take-upstream', action='append', default=[], help='明确采用上游的冲突路径')
    parser.add_argument('--allow-delete', action='store_true', help='允许计划中明确列出的源码删除')
    parser.add_argument('--checks', type=Path, help='操作者编写的验收argv数组JSON；不使用shell')
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if options.action == 'upgrade-plan':
            if options.source is None:
                parser.error('upgrade-plan必须提供--source底座仓库目录')
            result = upgrade_plan(root, options.source, options.ref)
            if options.output:
                with options.output.open('x', encoding='utf-8') as output:
                    output.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if options.action == 'upgrade-apply':
            if options.source is None or options.plan is None:
                parser.error('upgrade-apply必须提供--source和--plan')
            result = apply_upgrade(root, options.source, read_json(options.plan),
                keep_local=options.keep_local, take_upstream=options.take_upstream, allow_delete=options.allow_delete)
        elif options.action == 'upgrade-accept':
            if options.checks is None:
                parser.error('upgrade-accept必须提供操作者编写的--checks验收命令文件')
            result = accept_upgrade(root, read_json(options.checks))
        elif options.action == 'upgrade-restore':
            result = restore_upgrade(root)
        else:
            result = None
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        code = run_project(root, options.action)
        if code:
            parser.exit(code, '项目命令未成功，请检查本项目状态和日志\n')
    except (ProjectError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, '项目命令未完成：' + str(exc) + '\n')


if __name__ == '__main__':
    main()
