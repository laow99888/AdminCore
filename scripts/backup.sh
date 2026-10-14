#!/usr/bin/env bash
# AdminCore 备份：数据库（pg_dump）+ 媒体文件
# 产物：custom-format .dump、媒体归档及 SHA-256 清单。
# 用法：bash scripts/backup.sh

set -euo pipefail

cd "$(dirname "$0")/.."

# 自动/人工备份及恢复共享宿主锁；使用同一受限停写执行器。
exec "${ADMINCORE_PYTHON:-python3}" scripts/backup_runner.py --manual --backup-dir "${BACKUP_DIR:-backups}"
