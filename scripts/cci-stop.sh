#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${WEBAGENT_ROOT:-/mnt/afs/tj_share/webagent-cci}"
REPO_DIR="$ROOT_DIR/repo/WebAgent"
RUN_DIR="$ROOT_DIR/run"

stop_process() {
  local name="$1"
  local pid_file="$RUN_DIR/$name.pid"
  if [ ! -f "$pid_file" ]; then
    echo "$name: no pid file"
    return
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -z "$pid" ]; then
    rm -f "$pid_file"
    echo "$name: empty pid file removed"
    return
  fi
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" || true
    for _ in {1..20}; do
      if ! kill -0 "$pid" >/dev/null 2>&1; then
        break
      fi
      sleep 0.5
    done
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" || true
    fi
    echo "$name: stopped pid=$pid"
  else
    echo "$name: already stopped stale_pid=$pid"
  fi
  rm -f "$pid_file"
}

stop_process "webagent-web"
worker_pid_files=("$RUN_DIR"/webagent-worker*.pid)
if [ -e "${worker_pid_files[0]}" ]; then
  for worker_pid_file in "${worker_pid_files[@]}"; do
    stop_process "$(basename "$worker_pid_file" .pid)"
  done
else
  stop_process "webagent-worker"
fi
stop_process "webagent-api"
stop_process "openclaw-gateway"

stop_orphans_by_pattern() {
  local pattern="$1"
  local pids
  pids="$(pgrep -u "$(id -un)" -f "$pattern" || true)"
  if [ -z "$pids" ]; then
    echo "orphan cleanup: no process matched pattern=$pattern"
    return
  fi
  echo "orphan cleanup: TERM pids=$(echo "$pids" | tr '\n' ' ') pattern=$pattern"
  echo "$pids" | xargs -r kill || true
  sleep 2
  local survivors=""
  for pid in $pids; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      survivors="$survivors $pid"
    fi
  done
  if [ -n "$survivors" ]; then
    echo "orphan cleanup: KILL pids=$survivors pattern=$pattern"
    # shellcheck disable=SC2086
    kill -9 $survivors || true
  fi
}

for pattern in \
  "$ROOT_DIR/runtime/users/" \
  "$REPO_DIR/runtime/hermes-prompts/" \
  "$REPO_DIR/ppt_decks/" \
  "$ROOT_DIR/runtime/sensenova-skills/sn-ppt-workbench/" \
  "openclaw-agent" \
  "openclaw gateway run"
do
  stop_orphans_by_pattern "$pattern"
done
