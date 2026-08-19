#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${WEBAGENT_ROOT:-/mnt/afs/tj_share/webagent-cci}"
REPO_DIR="$ROOT_DIR/repo/WebAgent"
LOG_DIR="$ROOT_DIR/logs"
RUN_DIR="$ROOT_DIR/run"
PYTHON_BIN="$ROOT_DIR/runtime/conda-webagent/bin/python"
RUNTIME_BIN_DIR="$ROOT_DIR/runtime/conda-webagent/bin"
AGENT_ENV="$ROOT_DIR/secrets/agent-pack.env"
MODEL_SECRET_KEY_FILE="$ROOT_DIR/secrets/model-config.key"
AGENT_BIN_DIR="$ROOT_DIR/runtime/agent-home/.local/bin"
AGENT_HOME_DIR="$ROOT_DIR/runtime/agent-home"
HERMES_NODE_DIR="$ROOT_DIR/runtime/agent-home/.hermes/node/bin"
HERMES_PPT_EXPORT_DIR="$ROOT_DIR/runtime/agent-home/.hermes/skills/sn-ppt-standard/scripts/export_pptx"
WEB_PORT="${WEB_PORT:-3000}"
API_PORT="${API_PORT:-8010}"
WORKER_POOL="${WORKER_POOL:-solo}"
WORKER_CONCURRENCY="${WORKER_CONCURRENCY:-1}"
WORKER_INSTANCES="${WORKER_INSTANCES:-4}"
SHORT_CHAT_QUEUE_NAME="${SHORT_CHAT_QUEUE_NAME:-short-chat}"
AGENT_RUN_QUEUE_NAME="${AGENT_RUN_QUEUE_NAME:-agent-runs}"
CCI_MANAGE_LOCAL_INFRA="${CCI_MANAGE_LOCAL_INFRA:-true}"
POSTGRES_DATA_DIR="${POSTGRES_DATA_DIR:-$ROOT_DIR/runtime/postgres/data}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
REDIS_DATA_DIR="${REDIS_DATA_DIR:-$ROOT_DIR/runtime/redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
WEB_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-}"
WEB_PUBLIC_API_ADAPTER="${NEXT_PUBLIC_API_ADAPTER:-fastapi}"
DEFAULT_CORS_ORIGINS="http://localhost:$WEB_PORT,http://127.0.0.1:$WEB_PORT,http://localhost:3300,http://127.0.0.1:3300,http://localhost:3002,http://127.0.0.1:3002"

cd "$REPO_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$RUN_DIR"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing Python runtime: $PYTHON_BIN" >&2
  exit 1
fi

start_local_infrastructure() {
  if [ "$CCI_MANAGE_LOCAL_INFRA" != "true" ]; then
    return
  fi

  for command_name in pg_isready pg_ctl redis-cli redis-server; do
    if [ ! -x "$RUNTIME_BIN_DIR/$command_name" ]; then
      echo "Missing local infrastructure command: $RUNTIME_BIN_DIR/$command_name" >&2
      echo "Set CCI_MANAGE_LOCAL_INFRA=false when using external services." >&2
      exit 1
    fi
  done

  if ! "$RUNTIME_BIN_DIR/pg_isready" -h 127.0.0.1 -p "$POSTGRES_PORT" \
    >/dev/null 2>&1; then
    if [ ! -d "$POSTGRES_DATA_DIR" ] || [ ! -x "$RUNTIME_BIN_DIR/pg_ctl" ]; then
      echo "Local PostgreSQL runtime is incomplete under $ROOT_DIR/runtime." >&2
      exit 1
    fi
    echo "Starting local PostgreSQL on port $POSTGRES_PORT..."
    "$RUNTIME_BIN_DIR/pg_ctl" \
      -D "$POSTGRES_DATA_DIR" \
      -l "$LOG_DIR/postgres.log" \
      start
  fi

  if ! "$RUNTIME_BIN_DIR/redis-cli" -h 127.0.0.1 -p "$REDIS_PORT" ping \
    >/dev/null 2>&1; then
    if [ ! -x "$RUNTIME_BIN_DIR/redis-server" ]; then
      echo "Local Redis/Valkey runtime is incomplete under $ROOT_DIR/runtime." >&2
      exit 1
    fi
    echo "Starting local Redis/Valkey on port $REDIS_PORT..."
    mkdir -p "$REDIS_DATA_DIR"
    "$RUNTIME_BIN_DIR/redis-server" \
      --daemonize yes \
      --bind 127.0.0.1 \
      --port "$REDIS_PORT" \
      --dir "$REDIS_DATA_DIR" \
      --pidfile "$RUN_DIR/redis.pid" \
      --logfile "$LOG_DIR/redis.log"
  fi

  for attempt in {1..30}; do
    if "$RUNTIME_BIN_DIR/pg_isready" -h 127.0.0.1 -p "$POSTGRES_PORT" \
      >/dev/null 2>&1 && \
      "$RUNTIME_BIN_DIR/redis-cli" -h 127.0.0.1 -p "$REDIS_PORT" ping \
      >/dev/null 2>&1; then
      return
    fi
    if [ "$attempt" -eq 30 ]; then
      echo "Local PostgreSQL or Redis/Valkey did not become ready." >&2
      exit 1
    fi
    sleep 1
  done
}

start_local_infrastructure

if [ -f "$AGENT_ENV" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$AGENT_ENV"
  set +a
fi

if [ -z "${MODEL_CONFIG_ENCRYPTION_KEY:-}" ]; then
  mkdir -p "$(dirname "$MODEL_SECRET_KEY_FILE")"
  if [ ! -f "$MODEL_SECRET_KEY_FILE" ]; then
    umask 077
    "$PYTHON_BIN" -c \
      'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode("ascii"))' \
      > "$MODEL_SECRET_KEY_FILE"
    chmod 600 "$MODEL_SECRET_KEY_FILE"
  fi
  MODEL_CONFIG_ENCRYPTION_KEY="$(tr -d '\r\n' < "$MODEL_SECRET_KEY_FILE")"
  export MODEL_CONFIG_ENCRYPTION_KEY
fi

export PATH="$AGENT_BIN_DIR:$HERMES_NODE_DIR:$PATH"
export WEBAGENT_AGENT_PATH_PREFIX="$AGENT_BIN_DIR:$HERMES_NODE_DIR:$ROOT_DIR/runtime/conda-webagent/bin"
export LD_LIBRARY_PATH="$ROOT_DIR/runtime/conda-webagent/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$REPO_DIR/services/api"
export BACKEND_CORS_ORIGINS="${BACKEND_CORS_ORIGINS:-$DEFAULT_CORS_ORIGINS}"
export AGENT_RUN_QUEUE_NAME="$AGENT_RUN_QUEUE_NAME"
export SHORT_CHAT_QUEUE_NAME="$SHORT_CHAT_QUEUE_NAME"
export SN_API_KEY="${SN_API_KEY:-${SENSENOVA_API_KEY:-${OPENAI_API_KEY:-${LLM_API_KEY:-}}}}"
export SN_BASE_URL="${SN_BASE_URL:-${SENSENOVA_BASE_URL:-${OPENAI_BASE_URL:-${LLM_BASE_URL:-}}}}"
export SN_TEXT_API_KEY="${SN_TEXT_API_KEY:-$SN_API_KEY}"
export SN_CHAT_API_KEY="${SN_CHAT_API_KEY:-$SN_API_KEY}"
export SN_TEXT_BASE_URL="${SN_TEXT_BASE_URL:-$SN_BASE_URL}"
export SN_CHAT_BASE_URL="${SN_CHAT_BASE_URL:-$SN_BASE_URL}"

CA_BUNDLE="${SSL_CERT_FILE:-${REQUESTS_CA_BUNDLE:-}}"
if [ -n "$CA_BUNDLE" ] && [ ! -f "$CA_BUNDLE" ]; then
  unset SSL_CERT_FILE
  unset REQUESTS_CA_BUNDLE
fi
if [ -f /etc/ssl/certs/ca-certificates.crt ]; then
  export SSL_CERT_FILE="${SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}"
  export REQUESTS_CA_BUNDLE="${REQUESTS_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}"
fi

if ! command -v hermes >/dev/null 2>&1; then
  echo "Missing Hermes command on PATH." >&2
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import httpx
PY
then
  echo "Missing httpx in WebAgent Python runtime; installing into $PYTHON_BIN environment." >&2
  "$PYTHON_BIN" -m pip install httpx >> "$LOG_DIR/webagent-api.log" 2>&1 || {
    echo "Unable to install httpx automatically. PPT skills may fail inside Python stages." >&2
  }
fi

if command -v pnpm >/dev/null 2>&1; then
  if ! pnpm exec playwright --version >/dev/null 2>&1; then
    echo "Playwright CLI is unavailable from pnpm; PPTX export may not work." >&2
  elif ! pnpm exec playwright install chromium >> "$LOG_DIR/webagent-web.log" 2>&1; then
    echo "Playwright Chromium install failed. On CCI, install system browser dependencies or preinstall Chromium." >&2
  fi
fi

if [ -d "$HERMES_PPT_EXPORT_DIR" ] && command -v npx >/dev/null 2>&1; then
  if ! (cd "$HERMES_PPT_EXPORT_DIR" && npx playwright install chromium) >> "$LOG_DIR/webagent-web.log" 2>&1; then
    echo "Hermes PPT Playwright browser install failed. PPTX export may not work." >&2
  fi
fi

for pattern in \
  "uvicorn app.main:app --host 0.0.0.0 --port $API_PORT" \
  "celery -A app.workers.celery_app.celery_app worker" \
  "next start -H 0.0.0.0 -p $WEB_PORT" \
  "next start -H 0.0.0.0 -p 3002"
do
  pids="$(pgrep -u "$(id -un)" -f "$pattern" || true)"
  if [ -n "$pids" ]; then
    echo "$pids" | xargs -r kill
  fi
done

sleep 2

for pattern in \
  "uvicorn app.main:app --host 0.0.0.0 --port $API_PORT" \
  "celery -A app.workers.celery_app.celery_app worker" \
  "next start -H 0.0.0.0 -p $WEB_PORT" \
  "next start -H 0.0.0.0 -p 3002"
do
  pids="$(pgrep -u "$(id -un)" -f "$pattern" || true)"
  if [ -n "$pids" ]; then
    echo "$pids" | xargs -r kill -9
  fi
done

for pattern in \
  "$ROOT_DIR/runtime/users/" \
  "$REPO_DIR/runtime/hermes-prompts/" \
  "$REPO_DIR/ppt_decks/" \
  "$ROOT_DIR/runtime/sensenova-skills/sn-ppt-workbench/"
do
  pids="$(pgrep -u "$(id -un)" -f "$pattern" || true)"
  if [ -n "$pids" ]; then
    echo "$pids" | xargs -r kill
  fi
done

: > "$LOG_DIR/webagent-api.log"
echo "Applying database migrations..."
(
  cd "$REPO_DIR/services/api"
  "$PYTHON_BIN" -m alembic upgrade head
) >> "$LOG_DIR/webagent-api.log" 2>&1 || {
  echo "Database migration failed. See $LOG_DIR/webagent-api.log." >&2
  tail -n 80 "$LOG_DIR/webagent-api.log" >&2 || true
  exit 1
}

echo "Migrating stored model credentials..." >> "$LOG_DIR/webagent-api.log"
(
  cd "$REPO_DIR/services/api"
  "$PYTHON_BIN" scripts/migrate_model_secrets.py --apply
) >> "$LOG_DIR/webagent-api.log" 2>&1 || {
  echo "Model credential migration failed. See $LOG_DIR/webagent-api.log." >&2
  tail -n 80 "$LOG_DIR/webagent-api.log" >&2 || true
  exit 1
}

: > "$LOG_DIR/webagent-worker.log"
: > "$LOG_DIR/webagent-web.log"
rm -f "$RUN_DIR"/webagent-worker*.pid

nohup "$PYTHON_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT" \
  >> "$LOG_DIR/webagent-api.log" 2>&1 &
echo "$!" > "$RUN_DIR/webagent-api.pid"

nohup "$PYTHON_BIN" -m celery -A app.workers.celery_app.celery_app worker \
  --hostname="webagent-worker-short@%h" --loglevel=INFO -Q "$SHORT_CHAT_QUEUE_NAME" \
  --pool="$WORKER_POOL" --concurrency=1 \
  >> "$LOG_DIR/webagent-worker.log" 2>&1 &
echo "$!" > "$RUN_DIR/webagent-worker-short.pid"

for worker_index in $(seq 1 "$WORKER_INSTANCES"); do
  worker_name="webagent-worker-${worker_index}@%h"
  nohup "$PYTHON_BIN" -m celery -A app.workers.celery_app.celery_app worker \
    --hostname="$worker_name" --loglevel=INFO -Q "$AGENT_RUN_QUEUE_NAME" \
    --pool="$WORKER_POOL" --concurrency="$WORKER_CONCURRENCY" \
    >> "$LOG_DIR/webagent-worker.log" 2>&1 &
  echo "$!" > "$RUN_DIR/webagent-worker-${worker_index}.pid"
done

if ! command -v pnpm >/dev/null 2>&1; then
  echo "Missing pnpm on PATH; API and worker started, web was not started." >&2
else
  BUILD_ENV_STAMP="$REPO_DIR/apps/web/.next-build/.webagent-env"
  CURRENT_BUILD_ENV="NEXT_PUBLIC_API_BASE_URL=$WEB_PUBLIC_API_BASE_URL
NEXT_PUBLIC_API_ADAPTER=$WEB_PUBLIC_API_ADAPTER"
  WEB_SOURCE_CHANGED=false
  if [ -f "$BUILD_ENV_STAMP" ] && find \
    "$REPO_DIR/apps/web/src" \
    "$REPO_DIR/apps/web/package.json" \
    "$REPO_DIR/apps/web/next.config.ts" \
    -newer "$BUILD_ENV_STAMP" -print -quit | grep -q .; then
    WEB_SOURCE_CHANGED=true
  fi
  if [ ! -d "$REPO_DIR/apps/web/.next-build" ] || \
    [ ! -f "$BUILD_ENV_STAMP" ] || \
    [ "$(cat "$BUILD_ENV_STAMP" 2>/dev/null || true)" != "$CURRENT_BUILD_ENV" ] || \
    [ "$WEB_SOURCE_CHANGED" = true ]; then
    rm -rf "$REPO_DIR/apps/web/.next-build"
    NEXT_PUBLIC_API_BASE_URL="$WEB_PUBLIC_API_BASE_URL" \
    NEXT_PUBLIC_API_ADAPTER="$WEB_PUBLIC_API_ADAPTER" \
    pnpm --filter web build >> "$LOG_DIR/webagent-web.log" 2>&1
    printf "%s" "$CURRENT_BUILD_ENV" > "$BUILD_ENV_STAMP"
  fi
  NEXT_PUBLIC_API_BASE_URL="$WEB_PUBLIC_API_BASE_URL" \
  NEXT_PUBLIC_API_ADAPTER="$WEB_PUBLIC_API_ADAPTER" \
  nohup pnpm --filter web exec next start -H 0.0.0.0 -p "$WEB_PORT" \
    >> "$LOG_DIR/webagent-web.log" 2>&1 &
  echo "$!" > "$RUN_DIR/webagent-web.pid"
fi

for attempt in {1..60}; do
  if curl -fsS --max-time 2 "http://127.0.0.1:$API_PORT/api/health" >/tmp/webagent-api-health.txt 2>/dev/null; then
    cat /tmp/webagent-api-health.txt
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "FastAPI did not become healthy on port $API_PORT." >&2
    tail -n 80 "$LOG_DIR/webagent-api.log" >&2 || true
    exit 1
  fi
  sleep 1
done
echo
if command -v pnpm >/dev/null 2>&1; then
  for attempt in {1..60}; do
    if curl -fsS --max-time 2 "http://127.0.0.1:$WEB_PORT/app" >/dev/null 2>&1; then
      break
    fi
    if [ "$attempt" -eq 60 ]; then
      echo "Next.js did not become ready on port $WEB_PORT." >&2
      tail -n 120 "$LOG_DIR/webagent-web.log" >&2 || true
      exit 1
    fi
    sleep 1
  done
  echo "WebAgent web is listening on http://127.0.0.1:$WEB_PORT/app"
fi
pgrep -u "$(id -un)" -af "uvicorn app.main:app|celery -A app.workers.celery_app|next start -H 0.0.0.0 -p $WEB_PORT" || true
