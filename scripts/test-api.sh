#!/usr/bin/env bash
set -euo pipefail

GROUP="${1:-unit}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT_DIR/services/api"
PYTHON_BIN="${PYTHON_BIN:-$API_DIR/.venv/bin/python}"
export PYTHONPATH="$API_DIR${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Backend venv not found or not executable: $PYTHON_BIN" >&2
  exit 1
fi

integration_tests=(
  tests/test_agent_runtime_isolation.py
  tests/test_api_integration.py
)

mapfile -t all_tests < <(find tests -maxdepth 1 -type f -name 'test_*.py' -printf '%p\n' | sort)
unit_tests=()
for test_file in "${all_tests[@]}"; do
  if [[ " ${integration_tests[*]} " != *" $test_file "* ]]; then
    unit_tests+=("$test_file")
  fi
done

case "$GROUP" in
  unit)
    selected_tests=("${unit_tests[@]}")
    ;;
  integration)
    selected_tests=("${integration_tests[@]}")
    ;;
  all)
    selected_tests=("${all_tests[@]}")
    ;;
  *)
    echo "Usage: $0 [unit|integration|all] [extra pytest args...]" >&2
    exit 2
    ;;
esac

shift || true
cd "$API_DIR"
exec "$PYTHON_BIN" -m pytest "${selected_tests[@]}" -q --durations=10 "$@"
