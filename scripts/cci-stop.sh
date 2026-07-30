#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${WEBAGENT_ROOT:-/mnt/afs/tj_share/webagent-cci}"
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
stop_process "webagent-worker"
stop_process "webagent-api"
