"""生成项目的固定运维入口；不提供删除数据卷或自动升级覆盖。"""
import argparse
import json
from pathlib import Path
import subprocess

from create_project import ProjectError, run_project, upgrade_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['up', 'status', 'check', 'stop', 'upgrade-plan'])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--ref', default='HEAD')
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if options.action == 'upgrade-plan':
            if options.source is None:
                parser.error('upgrade-plan必须提供--source底座仓库目录')
            print(json.dumps(upgrade_plan(root, options.source, options.ref), ensure_ascii=False, indent=2))
            return
        code = run_project(root, options.action)
        if code:
            parser.exit(code, '项目命令未成功，请检查本项目状态和日志\n')
    except (ProjectError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, '项目命令未完成：' + str(exc) + '\n')


if __name__ == '__main__':
    main()
