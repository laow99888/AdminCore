#!/usr/bin/env bash
# AdminCore 备份：数据库（pg_dump）+ 媒体文件
# 产物：custom-format .dump、媒体归档及 SHA-256 清单。
# 用法：bash scripts/backup.sh

set -euo pipefail

cd "$(dirname "$0")/.."

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="${BACKUP_DIR:-backups}"
mkdir -p "$BACKUP_DIR"

DB_FILE="$BACKUP_DIR/admincore-db-$TIMESTAMP.dump"
MEDIA_FILE="$BACKUP_DIR/admincore-media-$TIMESTAMP.tar.gz"
MANIFEST="$BACKUP_DIR/admincore-$TIMESTAMP.sha256"

# 停止所有写入方，使数据库和媒体属于同一维护窗口。失败也恢复服务。
RUNNING=$(docker compose ps --status running --services | grep -E '^(frontend|worker|beat|backend)$' || true)
resume_services() {
  result=$?
  trap - EXIT
  if [ -n "$RUNNING" ]; then
    docker compose start $RUNNING || result=1
  fi
  exit "$result"
}
trap resume_services EXIT
docker compose stop frontend worker beat backend

echo ">>> 备份数据库 -> $DB_FILE"
docker compose exec -T db sh -c \
  'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$DB_FILE.partial"

echo ">>> 备份媒体文件 -> $MEDIA_FILE"
docker compose run --rm --no-deps -T --entrypoint python backend \
  /app/docker/media_backup.py > "$MEDIA_FILE.partial"
mv "$DB_FILE.partial" "$DB_FILE"
mv "$MEDIA_FILE.partial" "$MEDIA_FILE"
sha256sum "$DB_FILE" "$MEDIA_FILE" > "$MANIFEST.partial"
mv "$MANIFEST.partial" "$MANIFEST"

echo ">>> 备份完成："
ls -lh "$DB_FILE" "$MEDIA_FILE" "$MANIFEST"
echo "恢复命令：bash scripts/restore.sh $TIMESTAMP"
