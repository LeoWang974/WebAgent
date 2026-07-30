#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${WEBAGENT_ROOT:-/mnt/afs/tj_share/webagent-cci}"
LOG_DIR="$ROOT_DIR/logs"
RUN_DIR="$ROOT_DIR/run"
WEB_PORT="${WEB_PORT:-3000}"
API_PORT="${API_PORT:-8010}"

print_process() {
  local name="$1"
  local pid_file="$RUN_DIR/$name.pid"
  if [ ! -f "$pid_file" ]; then
    echo "$name: no pid file"
    return
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
    echo "$name: running pid=$pid"
  else
    echo "$name: stopped stale_pid=${pid:-unknown}"
  fi
}

echo "WebAgent CCI status"
echo "root: $ROOT_DIR"
echo "logs: $LOG_DIR"
print_process "webagent-api"
print_process "webagent-worker"
print_process "webagent-web"

if command -v curl >/dev/null 2>&1; then
  if curl -fsS "http://127.0.0.1:$API_PORT/api/health" >/tmp/webagent-api-health.txt; then
    printf "api health: "
    cat /tmp/webagent-api-health.txt
    echo
  else
    echo "api health: unavailable on 127.0.0.1:$API_PORT"
  fi
  if curl -fsS "http://127.0.0.1:$WEB_PORT/app" >/dev/null; then
    echo "web: ready on http://127.0.0.1:$WEB_PORT/app"
  else
    echo "web: unavailable on 127.0.0.1:$WEB_PORT"
  fi
fi

echo "recent logs:"
for log_name in webagent-api.log webagent-worker.log webagent-web.log; do
  log_path="$LOG_DIR/$log_name"
  if [ -f "$log_path" ]; then
    echo "- $log_path"
    tail -n 5 "$log_path" || true
  fi
done
