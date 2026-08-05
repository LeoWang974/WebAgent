#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${WEBAGENT_ROOT:-/mnt/afs/tj_share/webagent-cci}"
OPENCLAW_REPO="${OPENCLAW_REPO:-$ROOT_DIR/runtime/agent-home/.agent-pack/repos/openclaw}"

if [ ! -d "$OPENCLAW_REPO" ]; then
  echo "OpenClaw repo not found: $OPENCLAW_REPO" >&2
  exit 0
fi

python3 - "$OPENCLAW_REPO" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

repo = Path(sys.argv[1])

source_old = """    const idx = params.required.indexOf(original);
    if (idx !== -1) {
      params.required.splice(idx, 1);
      changed = true;
    }
"""
source_new = """    // Keep the canonical required key so models still see the mandatory
    // parameter. Alias keys remain available in properties and are normalized
    // at execution time.
"""

dist_old = """\t\tconst idx = params.required.indexOf(original);
\t\tif (idx !== -1) {
\t\t\tparams.required.splice(idx, 1);
\t\t\tchanged = true;
\t\t}
"""
dist_new = """\t\t// Keep the canonical required key so models still see the mandatory parameter.
"""

patched: list[str] = []
source_file = repo / "src" / "agents" / "pi-tools.params.ts"
if source_file.exists():
    text = source_file.read_text(encoding="utf-8")
    if source_old in text:
        source_file.write_text(text.replace(source_old, source_new), encoding="utf-8")
        patched.append(str(source_file))

for dist_file in sorted((repo / "dist").glob("pi-embedded-*.js")):
    text = dist_file.read_text(encoding="utf-8")
    if dist_old in text:
        dist_file.write_text(text.replace(dist_old, dist_new), encoding="utf-8")
        patched.append(str(dist_file))

if patched:
    print("Patched OpenClaw write tool schema:")
    for item in patched:
        print(f"- {item}")
else:
    print("OpenClaw write tool schema patch already applied or target pattern not found.")
PY

