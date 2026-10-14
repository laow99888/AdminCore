#!/usr/bin/env bash
# AdminCore 健康检查：compose 服务状态 + 后端 API + 前端页面
# 用法：bash scripts/health_check.sh [前端地址，默认 http://localhost]

set -u

FRONTEND_URL="${1:-http://localhost}"
API_URL="${FRONTEND_URL}/api/v1/health/"

fail=0

echo "== 容器状态 =="
docker compose ps --format 'table {{.Service}}\t{{.Status}}' || fail=1

echo
echo "== 后端 API $API_URL =="
if curl -fsS --retry 20 --retry-delay 2 --retry-all-errors "$API_URL" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'; then
  echo "OK"
else
  echo "FAIL：后端健康检查未通过"
  fail=1
fi

echo
echo "== 前端 $FRONTEND_URL =="
if curl -fsS "$FRONTEND_URL" > /dev/null; then
  echo "OK"
else
  echo "FAIL：前端页面不可达"
  fail=1
fi

echo
echo "== Celery worker =="
worker_ok=0
for attempt in {1..8}; do
  if docker compose exec -T worker celery -A config inspect ping --timeout 3 2>/dev/null | grep -q pong; then
    worker_ok=1
    break
  fi
  sleep 2
done
if [ "$worker_ok" -eq 1 ]; then
  echo "OK"
else
  echo "FAIL：Celery worker 无响应"
  fail=1
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "全部健康 ✔"
else
  echo "存在异常项，请检查上方输出 ✘"
fi
exit $fail
