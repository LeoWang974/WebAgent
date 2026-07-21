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

## mac Server Migration Notes

On macOS, use the same repo structure and environment variables, but replace Windows PowerShell launch scripts with shell/system service equivalents:

```bash
cd services/api
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010

cd apps/web
pnpm exec next start --port 3002
```

For production, run the frontend after `pnpm --filter web build`, place FastAPI and Next.js behind nginx/Caddy, and point Hermes paths in `services/api/.env` to the mac/server filesystem layout. Keep runtime outputs outside git-tracked directories and preserve the `.next` / `.next-build` separation.

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
are synced through WSL using `HERMES_WSL_DISTRIBUTION`. On a mac server, set
`HERMES_SKILLS_DIR` and `OPENCLAW_SKILLS_DIR` to normal mac filesystem paths.

Local development may use `python services/api/scripts/seed_local_users.py` to
create `test/test` and `admin/admin`. These accounts are local-only fixtures:
do not seed or keep them in production.

See `docs/PRODUCTION.md` for the deployment checklist.
