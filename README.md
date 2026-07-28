# WebAgent

WebAgent is a full-stack agent workspace with a Next.js frontend, FastAPI backend, PostgreSQL persistence, and Hermes/OpenClaw runtime adapters. The current development focus is a Codex-style workspace with conversations, Agent Run status, artifacts, settings, users, permissions, and browser-rendered Markdown/PPT/image/table previews.

## Repository Layout

```text
apps/web                Next.js frontend
services/api            FastAPI backend, SQLAlchemy models, Alembic migrations
services/agent-runtime  Hermes/OpenClaw adapter package
packages/shared         Shared frontend package
docs                    Product, architecture, and handoff notes
scripts                 Local development launch scripts
runtime                 Local runtime outputs, ignored by git
```

## Windows Development

Prerequisites:

- Node.js and pnpm
- Python 3.12 with `services/api/.venv`
- PostgreSQL running locally
- Hermes available through WSL2 if using the Hermes adapter

Install dependencies:

```powershell
pnpm install
cd services\api
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

Environment files:

- Root: copy `.env.example` if needed.
- Backend: `services/api/.env` is created from `services/api/.env.example` by `scripts/dev-api.ps1` when missing.
- Frontend: `apps/web/.env.local` is created from `apps/web/.env.local.example` by `scripts/dev-web.ps1` when missing.

Start both dev services:

```powershell
.\scripts\dev-all.ps1
```

Start one service at a time:

```powershell
.\scripts\dev-api.ps1
.\scripts\dev-web.ps1
```

Default URLs:

- API health: `http://127.0.0.1:8010/api/health`
- Web app: `http://localhost:3002/app`

The dev scripts stop stale listeners on their fixed ports before starting. Close the spawned PowerShell window or press `Ctrl+C` to stop a service.

## Local Docker Packaging

Docker packaging is provided for the WebAgent application services:

- `postgres`: PostgreSQL 16
- `redis`: Redis 7
- `api`: FastAPI + Alembic + WebAgent backend
- `worker`: Celery Agent Run worker that consumes Redis queued long tasks
- `web`: Next.js production server

Create the Docker environment file:

```powershell
Copy-Item .env.docker.example .env.docker
```

Then edit `.env.docker` and fill required secrets such as:

- `JWT_SECRET_KEY`
- `SENSENOVA_API_KEY`
- runtime addresses or binary paths for Hermes/OpenClaw

Build and start locally:

```powershell
docker compose --env-file .env.docker up --build
```

Open:

- Web app: `http://localhost:3002/app`
- API health: `http://localhost:8010/api/health`

Stop services:

```powershell
docker compose --env-file .env.docker down
```

Reset local Docker database and Redis volumes:

```powershell
docker compose --env-file .env.docker down -v
```

Important runtime note: the WebAgent images do not bundle Hermes, OpenClaw, or
agent_pack. They are expected to be installed on the host/server and exposed to
the API container through configured CLI paths, mounted directories, or gateway
URLs such as `OPENCLAW_BASE_URL=ws://host.docker.internal:18789`.

Docker mode enables queued Agent Runs by default:

- `AGENT_RUN_QUEUE_ENABLED=true`
- `AGENT_RUN_QUEUE_NAME=agent-runs`
- `AGENT_RUN_WORKSPACE_ROOT=/app/runtime/agent-runs`
- `WORKER_CONCURRENCY=1`
- `HERMES_ADAPTER_CONCURRENCY=1`
- `OPENCLAW_ADAPTER_CONCURRENCY=1`

In this mode the API process accepts the chat/SSE request and writes queued run
metadata, while the `worker` process executes Hermes/OpenClaw and writes run
events, messages, and artifacts back to PostgreSQL. Keep Redis and the worker
running for long tasks.

Start multiple worker containers locally:

```powershell
docker compose --env-file .env.docker up --build -d --scale worker=2
```

The recommended first production setting is multiple worker containers with
`WORKER_CONCURRENCY=1`, plus adapter-level Redis locks. This allows separate
queued jobs to be picked up quickly while keeping each runtime adapter within
its configured safe capacity. Increase `HERMES_ADAPTER_CONCURRENCY` or
`OPENCLAW_ADAPTER_CONCURRENCY` only after validating that the corresponding CLI,
gateway, credentials, and output directories are safe under parallel long tasks.

## Tests And Build

Backend:

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m compileall -q app ..\agent-runtime\agent_runtime
```

Frontend:

```powershell
pnpm --filter web test
pnpm --filter web build
```

## Next.js Build Directories

The frontend intentionally isolates dev and production output:

- Development server: `.next`
- Production build: `.next-build`

Both directories are ignored by git. Do not manually copy files into them or delete them while a dev server is running. If the dev build cache is corrupt, stop the dev server first, then run:

```powershell
pnpm --filter web run clean
```

`scripts/dev-web.ps1` performs this clean only before starting Next.js.

## Linux / CCI Server Notes

The next deployment target is a Linux CCI environment. The recommended shape is:

1. Install and validate agent_pack, Hermes, OpenClaw, SenseNova credentials, and
   Serper credentials in an isolated host directory.
2. Build WebAgent images from this repository.
3. Run WebAgent API/Web containers with PostgreSQL and Redis.
4. Connect the API container to the host-side Hermes/OpenClaw runtime through
   mounted paths or gateway URLs.
5. Verify login, conversations, Agent Run SSE, artifacts, sharing permissions,
   and long Hermes/OpenClaw tasks.

CCI web port convention:

- Web app: `http://<cci-host>:3000/app`
- API health: `http://<cci-host>:8010/api/health`
- `scripts/cci-start.sh` defaults to `WEB_PORT=3000` for bare Linux runs.
- Docker Compose can use the same convention by setting `WEB_PORT=3000`.

The Windows PowerShell scripts remain local development helpers, not Linux
service runners:

- `scripts/dev-api.ps1`: starts FastAPI on `127.0.0.1:8010`.
- `scripts/dev-web.ps1`: starts Next.js on `localhost:3002`.
- `scripts/dev-openclaw-gateway.ps1`: starts OpenClaw Gateway on
  `ws://127.0.0.1:18789`.
- `scripts/stop-dev.ps1`: stops `3002`, `8010`, and `18789`.

On Linux/CCI, replace them with Docker Compose, platform container settings, or
systemd/tmux only for host-side Hermes/OpenClaw helper processes.

## Agent Runtime And Search Configuration

WebAgent currently supports two runtime adapters:

- Hermes: stable path for long research, PPT, image, and artifact workflows.
- OpenClaw: integrated through the adapter pattern and gateway mode; long-task
  protocol work is ongoing.

The OpenClaw event contract expected by WebAgent is documented in:

```text
docs/OPENCLAW_EVENT_PROTOCOL.md
```

When the project moves to the mac server, deploy a Hermes/OpenClaw installation
that uses the same runtime contract. For OpenClaw, either keep the current
fallback behavior or deploy a protocol-capable fork/branch that emits
`openclaw.event.v1` events from `openclaw tasks list --json`.

Search configuration:

- Hermes should use `web.backend: serper` in its config.
- Hermes should have `SERPER_API_KEY` available in its runtime environment.
- OpenClaw should use `tools.web.search.provider = "serper"`.
- OpenClaw Gateway must be restarted after search provider changes.
- Tavily may remain configured for local experiments, but do not leave it as the
  default backend when validating Serper behavior.

Before testing long research on a new machine, verify Serper directly from the
same user account that runs the agent runtime:

```bash
python - <<'PY'
import json
import os
import urllib.request

key = os.environ["SERPER_API_KEY"]
req = urllib.request.Request(
    "https://google.serper.dev/search",
    data=json.dumps({"q": "WebAgent Serper connectivity test", "num": 1}).encode(),
    headers={"X-API-KEY": key, "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=20) as response:
    print(response.status)
PY
```

Expected output:

```text
200
```

## Production Configuration

Production templates are provided but contain placeholders:

- `.env.production.example`
- `apps/web/.env.production.example`
- `services/api/.env.production.example`

Required production settings:

- `NEXT_PUBLIC_API_ADAPTER=fastapi`
- `ENVIRONMENT=production`
- `ALLOW_DEV_AUTH_FALLBACK=false`
- `JWT_SECRET_KEY` must be a strong non-placeholder secret with at least 32 characters.
- `BACKEND_CORS_ORIGINS` must match the public web origin.

The frontend now rejects production builds unless the API adapter is explicitly
set to `fastapi`. The backend refuses to start in production when dev auth
fallback or an insecure JWT secret is configured.

The API also starts a lightweight cleanup loop when `CLEANUP_ENABLED=true`.
Admins can run it on demand through `POST /api/admin/cleanup`.

The API can also keep open-source SenseNova skills current for both Hermes and
OpenClaw. When `SKILLS_UPDATE_ENABLED=true`, FastAPI schedules a weekly update
from `https://github.com/OpenSenseNova/SenseNova-Skills.git`; the default
schedule is Friday 17:00 in `Asia/Shanghai`.

Relevant backend settings:

- `SKILLS_UPDATE_REPO_URL`
- `SKILLS_UPDATE_CACHE_DIR`
- `SKILLS_UPDATE_SOURCE_SUBDIR`
- `SKILLS_UPDATE_WEEKDAY`, `SKILLS_UPDATE_HOUR`, `SKILLS_UPDATE_MINUTE`
- `HERMES_SKILLS_DIR`, defaulting to `${HERMES_HOME}/skills`
- `OPENCLAW_SKILLS_DIR`, defaulting to `runtime/openclaw-skills`

On Windows development machines, Hermes paths such as `/home/.../.hermes/skills`
are synced through WSL using `HERMES_WSL_DISTRIBUTION`. On Linux/CCI, set
`HERMES_SKILLS_DIR` and `OPENCLAW_SKILLS_DIR` to normal Linux filesystem paths.

Local development may use `python services/api/scripts/seed_local_users.py` to
create `test/test` and `admin/admin`. These accounts are local-only fixtures:
do not seed or keep them in production.

See `docs/PRODUCTION.md` for the deployment checklist.

## Next Development Focus

After migration, the next planned development areas are:

- User multi-threading: allow users to run and observe multiple Agent Runs without
  blocking unrelated conversations.
- Linux/CCI deployment: validate Docker image build, runtime mounts, environment
  variables, and container networking.
- OpenClaw protocolization: move from fallback text/directory discovery toward
  explicit `openclaw.event.v1` events.
- Permission hardening: continue validating private, shared, and public session
  behavior across users.
- Artifact stability: keep run-scoped artifact selection deterministic when a
  run generates Markdown, HTML, PPTX, images, tables, and debug JSON.
