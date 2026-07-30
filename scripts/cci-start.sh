#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${WEBAGENT_ROOT:-/mnt/afs/tj_share/webagent-cci}"
REPO_DIR="$ROOT_DIR/repo/WebAgent"
LOG_DIR="$ROOT_DIR/logs"
RUN_DIR="$ROOT_DIR/run"
PYTHON_BIN="$ROOT_DIR/runtime/conda-webagent/bin/python"
AGENT_ENV="$ROOT_DIR/secrets/agent-pack.env"
AGENT_BIN_DIR="$ROOT_DIR/runtime/agent-home/.local/bin"
HERMES_NODE_DIR="$ROOT_DIR/runtime/agent-home/.hermes/node/bin"
WEB_PORT="${WEB_PORT:-3000}"
API_PORT="${API_PORT:-8010}"
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

if [ -f "$AGENT_ENV" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$AGENT_ENV"
  set +a
fi

export PATH="$AGENT_BIN_DIR:$HERMES_NODE_DIR:$PATH"
export PYTHONPATH="$REPO_DIR/services/api:$REPO_DIR/services/agent-runtime"
export BACKEND_CORS_ORIGINS="${BACKEND_CORS_ORIGINS:-$DEFAULT_CORS_ORIGINS}"
export SN_API_KEY="${SN_API_KEY:-${SENSENOVA_API_KEY:-${OPENAI_API_KEY:-${LLM_API_KEY:-}}}}"
export SN_BASE_URL="${SN_BASE_URL:-${SENSENOVA_BASE_URL:-${OPENAI_BASE_URL:-${LLM_BASE_URL:-}}}}"

CA_BUNDLE="${SSL_CERT_FILE:-${REQUESTS_CA_BUNDLE:-}}"
if [ -n "$CA_BUNDLE" ] && [ ! -f "$CA_BUNDLE" ]; then
  unset SSL_CERT_FILE
  unset REQUESTS_CA_BUNDLE
fi
if [ -f /etc/ssl/certs/ca-certificates.crt ]; then
  export SSL_CERT_FILE="${SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}"
  export REQUESTS_CA_BUNDLE="${REQUESTS_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}"
fi

for command_name in hermes openclaw; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing agent command on PATH: $command_name" >&2
    exit 1
  fi
done

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

: > "$LOG_DIR/webagent-api.log"
: > "$LOG_DIR/webagent-worker.log"
: > "$LOG_DIR/webagent-web.log"

nohup "$PYTHON_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT" \
  >> "$LOG_DIR/webagent-api.log" 2>&1 &
echo "$!" > "$RUN_DIR/webagent-api.pid"
nohup "$PYTHON_BIN" -m celery -A app.workers.celery_app.celery_app worker \
  --loglevel=INFO -Q agent-runs --concurrency="${WORKER_CONCURRENCY:-2}" \
  >> "$LOG_DIR/webagent-worker.log" 2>&1 &
echo "$!" > "$RUN_DIR/webagent-worker.pid"

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

for attempt in {1..30}; do
  if curl -fsS "http://127.0.0.1:$API_PORT/api/health" >/tmp/webagent-api-health.txt; then
    cat /tmp/webagent-api-health.txt
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "FastAPI did not become healthy on port $API_PORT." >&2
    tail -n 80 "$LOG_DIR/webagent-api.log" >&2 || true
    exit 1
  fi
  sleep 1
done
echo
if command -v pnpm >/dev/null 2>&1; then
  for attempt in {1..30}; do
    if curl -fsS "http://127.0.0.1:$WEB_PORT/app" >/dev/null; then
      break
    fi
    if [ "$attempt" -eq 30 ]; then
      echo "Next.js did not become ready on port $WEB_PORT." >&2
      tail -n 120 "$LOG_DIR/webagent-web.log" >&2 || true
      exit 1
    fi
    sleep 1
  done
  echo "WebAgent web is listening on http://127.0.0.1:$WEB_PORT/app"
fi
pgrep -u "$(id -un)" -af "uvicorn app.main:app|celery -A app.workers.celery_app|next start -H 0.0.0.0 -p $WEB_PORT" || true
