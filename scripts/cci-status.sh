#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${WEBAGENT_ROOT:-/mnt/afs/tj_share/webagent-cci}"
REPO_DIR="$ROOT_DIR/repo/WebAgent"
LOG_DIR="$ROOT_DIR/logs"
RUN_DIR="$ROOT_DIR/run"
PYTHON_BIN="$ROOT_DIR/runtime/conda-webagent/bin/python"
AGENT_BIN_DIR="$ROOT_DIR/runtime/agent-home/.local/bin"
AGENT_HOME_DIR="$ROOT_DIR/runtime/agent-home"
HERMES_NODE_DIR="$ROOT_DIR/runtime/agent-home/.hermes/node/bin"
WEB_PORT="${WEB_PORT:-3000}"
API_PORT="${API_PORT:-8010}"
OPENCLAW_GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"

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
worker_pid_files=("$RUN_DIR"/webagent-worker*.pid)
if [ -e "${worker_pid_files[0]}" ]; then
  for worker_pid_file in "${worker_pid_files[@]}"; do
    worker_name="$(basename "$worker_pid_file" .pid)"
    print_process "$worker_name"
  done
else
  print_process "webagent-worker"
fi
print_process "webagent-web"
print_process "openclaw-gateway"

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

if [ -x "$PYTHON_BIN" ]; then
  PYTHONPATH="$REPO_DIR/services/api:$REPO_DIR/services/agent-runtime" "$PYTHON_BIN" - <<'PY'
from app.core.config import settings

print("runtime checks:")
try:
    import redis

    client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
    client.ping()
    print("redis: ok")
except Exception as error:
    print(f"redis: unavailable ({error})")

try:
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine

    async def check_postgresql() -> None:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        async with engine.connect() as connection:
            await connection.exec_driver_sql("select 1")
        await engine.dispose()

    asyncio.run(check_postgresql())
    print("postgresql: ok")
except Exception as error:
    print(f"postgresql: unavailable ({error})")
PY
else
  echo "runtime checks: missing Python runtime $PYTHON_BIN"
fi

PATH="$AGENT_BIN_DIR:$HERMES_NODE_DIR:$ROOT_DIR/runtime/conda-webagent/bin:$PATH"
for command_name in hermes openclaw; do
  if command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name: available ($(command -v "$command_name"))"
  else
    echo "$command_name: unavailable on PATH"
  fi
done

if [ -x "$PYTHON_BIN" ]; then
  if "$PYTHON_BIN" - "$OPENCLAW_GATEWAY_PORT" <<'PY' >/dev/null 2>&1
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket()
sock.settimeout(1)
sock.connect(("127.0.0.1", port))
sock.close()
PY
  then
    echo "openclaw gateway: ready on ws://127.0.0.1:$OPENCLAW_GATEWAY_PORT"
  else
    echo "openclaw gateway: unavailable on ws://127.0.0.1:$OPENCLAW_GATEWAY_PORT"
  fi
fi

echo "recent logs:"
for log_name in webagent-api.log webagent-worker.log webagent-web.log openclaw-gateway.log; do
  log_path="$LOG_DIR/$log_name"
  if [ -f "$log_path" ]; then
    echo "- $log_path"
    tail -n 5 "$log_path" || true
  fi
done
