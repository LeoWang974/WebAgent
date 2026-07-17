# Production Deployment

This project is not yet packaged as a one-command production installer. Use this
checklist when moving the current checkpoint to a Mac or Linux server.

## Required Environment

- Node.js and pnpm
- Python 3.12
- PostgreSQL
- Redis
- Hermes CLI installed on the server account that runs the API
- A reverse proxy such as nginx or Caddy for HTTPS

## Environment Files

Use these templates and replace every placeholder:

- Root overview: `.env.production.example`
- Frontend: `apps/web/.env.production.example`
- Backend: `services/api/.env.production.example`

Production must use:

```text
NEXT_PUBLIC_API_ADAPTER=fastapi
ENVIRONMENT=production
ALLOW_DEV_AUTH_FALLBACK=false
JWT_SECRET_KEY=<at least 32 random characters>
```

The API refuses to start in production if `ALLOW_DEV_AUTH_FALLBACK=true` or the
JWT secret is still a development placeholder.

Do not run `services/api/scripts/seed_local_users.py` in production. The
`test/test` and `admin/admin` accounts created by that script are local
development fixtures only.

## Backend

```bash
cd services/api
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

For long-running service management, run the uvicorn command through `systemd`,
`launchd`, `supervisord`, or another process manager.

## Frontend

```bash
pnpm install
pnpm --filter web build
pnpm --filter web exec next start --port 3002
```

Set `NEXT_PUBLIC_API_BASE_URL` to the public HTTPS API origin used by the
browser, for example `https://api.example.com`.

## Reverse Proxy

Recommended public layout:

- `https://app.example.com` -> Next.js on `127.0.0.1:3002`
- `https://api.example.com` -> FastAPI on `127.0.0.1:8010`

Set backend CORS accordingly:

```text
BACKEND_CORS_ORIGINS=https://app.example.com
```

## Preflight Checks

Run before exposing the service:

```bash
cd services/api
pytest
alembic current

cd ../..
pnpm --filter web test
pnpm --filter web build
```

Then verify:

- `GET https://api.example.com/api/health` returns `{"status":"ok"}`.
- The web app loads with no mock responses.
- Login works with a real user.
- A Hermes run creates Agent Run events and artifacts.
- Generated artifacts are stored outside git-tracked directories.

## Operational Notes

- Keep `runtime/`, logs, and generated reports out of git.
- Data cleanup runs inside the FastAPI lifespan when `CLEANUP_ENABLED=true`.
  It removes expired runtime files, orphan artifacts, and long-disconnected
  runs. Tune `CLEANUP_INTERVAL_SECONDS`, `CLEANUP_RUNTIME_FILE_MAX_AGE_DAYS`,
  and `CLEANUP_DISCONNECTED_RUN_MAX_AGE_DAYS` for the server.
- Admins can manually trigger cleanup with `POST /api/admin/cleanup`.
- Do not use the Windows PowerShell dev scripts on macOS production; they are
  development conveniences only.
