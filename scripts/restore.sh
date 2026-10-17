#!/usr/bin/env bash
# AdminCore 恢复：从 backups/admincore-{db,media}-<时间戳> 恢复
# 用法：bash scripts/restore.sh <时间戳>   （时间戳见 backup.sh 输出）

set -euo pipefail

# Git Bash 调用 docker.exe 时必须保留容器的 /app/... 参数。
case "${OSTYPE:-}" in
  msys*|cygwin*) export MSYS_NO_PATHCONV=1 ;;
esac

cd "$(dirname "$0")/.."

TIMESTAMP="${1:?用法：bash scripts/restore.sh <时间戳>}"
[[ "$TIMESTAMP" =~ ^[0-9]{8}-[0-9]{6}$ ]] || { echo '时间戳格式无效'; exit 1; }
BACKUP_DIR="${BACKUP_DIR:-backups}"
if [ "${ADMINCORE_BACKUP_COORDINATED:-0}" != "1" ]; then
  exec "${ADMINCORE_PYTHON:-python3}" scripts/backup_runner.py --restore "$TIMESTAMP" --backup-dir "$BACKUP_DIR"
fi
DB_FILE="$BACKUP_DIR/admincore-db-$TIMESTAMP.dump"
MEDIA_FILE="$BACKUP_DIR/admincore-media-$TIMESTAMP.tar.gz"
MANIFEST="$BACKUP_DIR/admincore-$TIMESTAMP.sha256"
TOKEN="$TIMESTAMP-$$"
STAGING="admincore_restore_${TIMESTAMP//-/_}_$$"
ROLLBACK="admincore_rollback_${TIMESTAMP//-/_}_$$"

[ -f "$DB_FILE" ] && [ -f "$MEDIA_FILE" ] && [ -f "$MANIFEST" ] || { echo '缺少完整的新格式备份；旧 SQL 备份请按文档在隔离库转换'; exit 1; }
# 只验证固定的两个文件，不能让清单指定任意读取路径。
# Git Bash 默认输出二进制标记 *；显式文本格式使清单与 Linux 一致。
EXPECTED=$(sha256sum --text "$DB_FILE" "$MEDIA_FILE")
# 自动执行器使用固定 basename，允许独立目录迁移；兼容旧脚本的路径清单。
PORTABLE=$(cd "$BACKUP_DIR" && sha256sum --text "admincore-db-$TIMESTAMP.dump" "admincore-media-$TIMESTAMP.tar.gz")
ACTUAL=$(cat "$MANIFEST")
[ "$EXPECTED" = "$ACTUAL" ] || [ "$PORTABLE" = "$ACTUAL" ] || { echo '备份校验失败'; exit 1; }

echo "!!! 将验证并切换到 $TIMESTAMP 备份；当前数据库和媒体保留为回滚副本。"
if [ "${ADMINCORE_RESTORE_CONFIRMED:-0}" = "1" ]; then
  answer=yes
else
  read -r -p "输入 yes 确认：" answer
  [ "$answer" = "yes" ] || { echo "已取消"; exit 1; }
fi

STOPPED=0
SWAPPED=0
MEDIA_STARTED=0
COMPLETED=0
RUNNING=$(docker compose ps --status running --services | grep -E '^(frontend|realtime|worker|beat|backend)$' || true)
ROLLBACK_OK=1
cleanup() {
  result=$?
  trap - EXIT
  if [ "$COMPLETED" = 0 ] && [ "$SWAPPED" = 1 ]; then
    echo '!!! 恢复失败，回滚数据库与媒体；保留失败现场。'
    STOPPED=1
    if [ -n "$RUNNING" ]; then docker compose stop $RUNNING || ROLLBACK_OK=0; fi
    if [ "$MEDIA_STARTED" = 1 ]; then
      docker compose run --rm --no-deps -T --entrypoint python backend /app/docker/media_restore.py rollback "$TOKEN" || ROLLBACK_OK=0
    fi
    docker compose exec -T db sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -v original="$POSTGRES_DB" -v old="$1" -v failed="$2"' sh "$ROLLBACK" "${STAGING}_failed" <<'SQL' || ROLLBACK_OK=0
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'original' AND pid <> pg_backend_pid();
BEGIN;
ALTER DATABASE :"original" RENAME TO :"failed";
ALTER DATABASE :"old" RENAME TO :"original";
COMMIT;
SQL
  fi
  if [ "$STOPPED" = 1 ] && [ "$ROLLBACK_OK" = 1 ] && [ -n "$RUNNING" ]; then
    docker compose start $RUNNING || result=1
  elif [ "$ROLLBACK_OK" = 0 ]; then
    echo '!!! 自动回滚未完全成功，服务保持停止，请人工检查保留副本。'
    result=1
  fi
  if [ "$COMPLETED" = 0 ]; then
    echo "!!! 未完成恢复。保留检查数据库 $STAGING 与媒体 staging $TOKEN，请检查日志。"
  fi
  exit "$result"
}
trap cleanup EXIT

echo '>>> 在独立数据库验证归档...'
docker compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$STAGING"
docker compose exec -T db sh -c 'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$1"' sh "$STAGING" < "$DB_FILE"
docker compose exec -T db sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -c "SELECT count(*) FROM django_migrations"' sh "$STAGING"

echo '>>> 验证媒体路径并解压到 staging，当前媒体保持可用...'
docker compose run --rm --no-deps -T --entrypoint python backend /app/docker/media_restore.py prepare "$TOKEN" < "$MEDIA_FILE"

echo '>>> 停写并切换数据库...'
STOPPED=1
if [ -n "$RUNNING" ]; then docker compose stop $RUNNING; fi
docker compose exec -T db sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -v original="$POSTGRES_DB" -v stage="$1" -v old="$2"' sh "$STAGING" "$ROLLBACK" <<'SQL'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'original' AND pid <> pg_backend_pid();
BEGIN;
ALTER DATABASE :"original" RENAME TO :"old";
ALTER DATABASE :"stage" RENAME TO :"original";
COMMIT;
SQL
SWAPPED=1
MEDIA_STARTED=1
docker compose run --rm --no-deps -T --entrypoint python backend /app/docker/media_restore.py commit "$TOKEN"
if [ -n "$RUNNING" ]; then docker compose start $RUNNING; fi
STOPPED=0
bash scripts/health_check.sh "${FRONTEND_URL:-http://localhost}"
COMPLETED=1
echo "恢复完成；旧库 $ROLLBACK 保留；本地模式的旧媒体在 /app/media/.admincore-restore-$TOKEN/old，对象模式在配置的媒体前缀下 .admincore-restore-$TOKEN/old。确认业务验收后人工清理。"
