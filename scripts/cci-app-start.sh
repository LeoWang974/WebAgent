#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${WEBAGENT_ROOT:-/mnt/afs/tj_share/webagent-cci}"
REPO_DIR="$ROOT_DIR/repo/WebAgent"
LOG_DIR="$ROOT_DIR/logs"
RUN_DIR="$ROOT_DIR/run"
AGENT_HOME="$ROOT_DIR/runtime/agent-home"
PYTHON_HOME="$ROOT_DIR/runtime/conda-webagent"
WEB_PORT="${WEB_PORT:-3000}"
API_PORT="${API_PORT:-8010}"

fail() {
  echo "[ERROR] $*" >&2
  exit 1
}

ensure_runtime_user() {
  local runtime_uid runtime_gid runtime_user runtime_group

  runtime_uid="$(stat -c %u "$ROOT_DIR")"
  runtime_gid="$(stat -c %g "$ROOT_DIR")"

  if [ "$runtime_uid" -eq 0 ]; then
    fail "The persistent WebAgent directory must not be owned by root."
  fi

  runtime_group="$(getent group "$runtime_gid" | cut -d: -f1 || true)"
  if [ -z "$runtime_group" ]; then
    runtime_group="webagent-runtime"
    if getent group "$runtime_group" >/dev/null 2>&1; then
      runtime_group="webagent-runtime-$runtime_gid"
    fi
    groupadd --gid "$runtime_gid" "$runtime_group"
  fi

  runtime_user="$(getent passwd "$runtime_uid" | cut -d: -f1 || true)"
  if [ -z "$runtime_user" ]; then
    runtime_user="webagent-runtime"
    if getent passwd "$runtime_user" >/dev/null 2>&1; then
      runtime_user="webagent-runtime-$runtime_uid"
    fi
    useradd \
      --uid "$runtime_uid" \
      --gid "$runtime_gid" \
      --home-dir "$AGENT_HOME" \
      --no-create-home \
      --shell /bin/bash \
      "$runtime_user"
  fi

  echo "[BOOT] dropping privileges to $runtime_user ($runtime_uid:$runtime_gid)"
  exec runuser --user "$runtime_user" -- env \
    WEBAGENT_ROOT="$ROOT_DIR" \
    WEB_PORT="$WEB_PORT" \
    API_PORT="$API_PORT" \
    HOME="$AGENT_HOME" \
    HERMES_HOME="$AGENT_HOME/.hermes" \
    XDG_CACHE_HOME="/mnt/afs/tj_share/.cache" \
    PLAYWRIGHT_BROWSERS_PATH="/mnt/afs/tj_share/.cache/ms-playwright" \
    PATH="$AGENT_HOME/.local/bin:$AGENT_HOME/.hermes/node/bin:$PYTHON_HOME/bin:/usr/local/bin:/usr/bin:/bin" \
    LD_LIBRARY_PATH="$PYTHON_HOME/lib:${LD_LIBRARY_PATH:-}" \
    API_INTERNAL_BASE_URL="http://127.0.0.1:$API_PORT" \
    NEXT_PUBLIC_API_BASE_URL="" \
    NEXT_PUBLIC_API_ADAPTER="fastapi" \
    CCI_MANAGE_LOCAL_INFRA="true" \
    /bin/bash "$0" "$@"
}

if [ "$(id -u)" -eq 0 ]; then
  command -v getent >/dev/null 2>&1 || fail "getent is required."
  command -v groupadd >/dev/null 2>&1 || fail "groupadd is required."
  command -v useradd >/dev/null 2>&1 || fail "useradd is required."
  command -v runuser >/dev/null 2>&1 || fail "runuser is required."
  [ -d "$ROOT_DIR" ] || fail "Required directory does not exist: $ROOT_DIR"
  ensure_runtime_user "$@"
fi

echo "[BOOT] $(date -Is) hostname=$(hostname) uid=$(id -u) gid=$(id -g)"
echo "[BOOT] WebAgent root: $ROOT_DIR"
echo "[BOOT] public port: $WEB_PORT; internal API port: $API_PORT"

[ -d "$REPO_DIR" ] || fail "Required repository does not exist: $REPO_DIR"
[ -x "$PYTHON_HOME/bin/python" ] || fail "Missing Python runtime."
[ -x "$AGENT_HOME/.local/bin/hermes" ] || fail "Missing Hermes runtime."
[ -x "$AGENT_HOME/.local/bin/pnpm" ] || fail "Missing pnpm runtime."
[ -f "$REPO_DIR/services/api/.env" ] || fail "Missing services/api/.env."
[ -f "$ROOT_DIR/secrets/agent-pack.env" ] || fail "Missing agent-pack.env."

mkdir -p "$LOG_DIR" "$RUN_DIR"
cd "$REPO_DIR"

maintenance_lock="$RUN_DIR/maintenance.lock"
if [ -f "$maintenance_lock" ]; then
  echo "[WAIT] maintenance lock is active: $maintenance_lock"
  while [ -f "$maintenance_lock" ]; do
    sleep 5
  done
  echo "[WAIT] maintenance lock released"
fi

ensure_cryptography_compatibility() {
  local compat_wheel

  if "$PYTHON_HOME/bin/python" -c \
    'from cryptography.fernet import Fernet' >/dev/null 2>&1; then
    return
  fi

  compat_wheel="$ROOT_DIR/runtime/compat-wheels/cryptography-49.0.0-cp311-abi3-manylinux_2_28_x86_64.whl"
  [ -f "$compat_wheel" ] || fail \
    "cryptography is incompatible and the cached compatibility wheel is missing."

  echo "[COMPAT] installing cached manylinux_2_28 cryptography wheel"
  "$PYTHON_HOME/bin/python" -m pip install \
    --force-reinstall --no-deps "$compat_wheel"
  "$PYTHON_HOME/bin/python" -c \
    'from cryptography.fernet import Fernet' >/dev/null 2>&1 || fail \
    "cryptography remains unavailable after compatibility repair."
}

ensure_cryptography_compatibility

tail_pid=""

cleanup() {
  local exit_code=$?
  trap - EXIT TERM INT
  echo "[STOP] stopping WebAgent processes"
  if [ -n "$tail_pid" ]; then
    kill "$tail_pid" >/dev/null 2>&1 || true
  fi
  WEBAGENT_ROOT="$ROOT_DIR" bash scripts/cci-stop.sh || true

  if [ "${CCI_MANAGE_LOCAL_INFRA:-true}" = "true" ]; then
    echo "[STOP] stopping local Redis/Valkey and PostgreSQL"
    "$PYTHON_HOME/bin/redis-cli" -h 127.0.0.1 -p 6379 \
      shutdown nosave >/dev/null 2>&1 || true
    "$PYTHON_HOME/bin/pg_ctl" -D "$ROOT_DIR/runtime/postgres/data" \
      stop -m fast >/dev/null 2>&1 || true
  fi

  exit "$exit_code"
}

trap cleanup EXIT
trap 'exit 0' TERM INT

echo "[START] launching WebAgent"
bash scripts/cci-start.sh
bash scripts/cci-status.sh

echo "[READY] WebAgent is available on 0.0.0.0:$WEB_PORT/app"
tail -n 40 -F \
  "$LOG_DIR/webagent-api.log" \
  "$LOG_DIR/webagent-worker.log" \
  "$LOG_DIR/webagent-web.log" &
tail_pid=$!

health_failures=0
while true; do
  sleep 10
  if curl -fsS --max-time 5 "http://127.0.0.1:$API_PORT/api/health" \
      >/dev/null 2>&1 && \
    curl -fsS --max-time 5 "http://127.0.0.1:$WEB_PORT/app" \
      >/dev/null 2>&1; then
    health_failures=0
    continue
  fi

  health_failures=$((health_failures + 1))
  echo "[WARN] health check failed: count=$health_failures"
  if [ "$health_failures" -ge 6 ]; then
    fail "WebAgent remained unhealthy for approximately 60 seconds."
  fi
done
