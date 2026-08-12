#!/usr/bin/env bash
set -euo pipefail

GROUP="${1:-unit}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT_DIR/services/api"
PYTHON_BIN="${PYTHON_BIN:-$API_DIR/.venv/bin/python}"
export PYTHONPATH="$API_DIR:$ROOT_DIR/services/agent-runtime${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Backend venv not found or not executable: $PYTHON_BIN" >&2
  exit 1
fi

unit_tests=(
  tests/test_artifact_discovery.py
  tests/test_agent_run_artifact_service.py
  tests/test_agent_run_queue.py
  tests/test_artifact_slides.py
  tests/test_cleanup.py
  tests/test_hermes_adapter.py
  tests/test_hermes_env.py
  tests/test_hermes_protocol.py
  tests/test_model_runtime_config.py
  tests/test_model_runtime_health.py
  tests/test_runtime_context_builder.py
  tests/test_skills_update.py
  tests/test_source_encoding.py
)

integration_tests=(
  tests/test_agent_runtime_isolation.py
  tests/test_api_integration.py
)

case "$GROUP" in
  unit)
    selected_tests=("${unit_tests[@]}")
    ;;
  integration)
    selected_tests=("${integration_tests[@]}")
    ;;
  all)
    selected_tests=("${unit_tests[@]}" "${integration_tests[@]}")
    ;;
  *)
    echo "Usage: $0 [unit|integration|all] [extra pytest args...]" >&2
    exit 2
    ;;
esac

shift || true
cd "$API_DIR"
exec "$PYTHON_BIN" -m pytest "${selected_tests[@]}" -q --durations=10 "$@"
