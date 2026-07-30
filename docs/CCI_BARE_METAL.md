# CCI Bare-Metal Runbook

CCI does not run Docker for this project. Treat host processes as the production path and use `scripts/cci-start.sh` as the only start entry.

## Directory Contract

Default root:

```bash
/mnt/afs/tj_share/webagent-cci
```

Expected layout:

```text
/mnt/afs/tj_share/webagent-cci/
  repo/WebAgent/                 # Git checkout
  runtime/conda-webagent/bin/python
  runtime/agent-home/.local/bin/ # hermes/openclaw commands
  runtime/agent-home/.hermes/node/bin
  logs/
  run/
  secrets/agent-pack.env
```

Override the root with:

```bash
export WEBAGENT_ROOT=/path/to/isolated/webagent-cci
```

## Required Runtime

- Python: `runtime/conda-webagent/bin/python`
- Node.js/pnpm: `pnpm` must be on `PATH`
- Redis: configured by `REDIS_URL`
- PostgreSQL: configured by `DATABASE_URL`
- Hermes CLI: `hermes` must be on `PATH`
- OpenClaw CLI/Gateway: `openclaw` must be on `PATH`; set gateway URL when needed

`scripts/cci-start.sh` prepends these agent paths:

```bash
$WEBAGENT_ROOT/runtime/agent-home/.local/bin
$WEBAGENT_ROOT/runtime/agent-home/.hermes/node/bin
```

## Required `agent-pack.env`

Create:

```bash
$WEBAGENT_ROOT/secrets/agent-pack.env
```

Minimum variables:

```bash
DATABASE_URL=postgresql+asyncpg://webagent:password@127.0.0.1:5432/webagent
REDIS_URL=redis://127.0.0.1:6379/0
JWT_SECRET_KEY=replace-with-a-long-random-secret

SENSENOVA_API_KEY=sk-...
SENSENOVA_BASE_URL=https://token.sensenova.cn/v1
SERPER_API_KEY=...

HERMES_HOME=/mnt/afs/tj_share/webagent-cci/runtime/agent-home/.hermes
HERMES_SKILLS_DIR=/mnt/afs/tj_share/webagent-cci/runtime/agent-home/.hermes/skills
OPENCLAW_SKILLS_DIR=/mnt/afs/tj_share/webagent-cci/runtime/agent-home/.openclaw/skills
OPENCLAW_BASE_URL=ws://127.0.0.1:18789

AGENT_RUN_QUEUE_ENABLED=true
WORKER_CONCURRENCY=2
BACKEND_CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
```

Do not commit real keys.

## Start, Status, Stop

```bash
cd /mnt/afs/tj_share/webagent-cci/repo/WebAgent
WEB_PORT=3000 API_PORT=8010 bash scripts/cci-start.sh
bash scripts/cci-status.sh
bash scripts/cci-stop.sh
```

`cci-start.sh` starts:

- FastAPI on `0.0.0.0:8010`
- Celery worker on queue `agent-runs`
- Next.js on `0.0.0.0:3000`

## Logs

Default logs:

```text
/mnt/afs/tj_share/webagent-cci/logs/webagent-api.log
/mnt/afs/tj_share/webagent-cci/logs/webagent-worker.log
/mnt/afs/tj_share/webagent-cci/logs/webagent-web.log
```

PID files:

```text
/mnt/afs/tj_share/webagent-cci/run/webagent-api.pid
/mnt/afs/tj_share/webagent-cci/run/webagent-worker.pid
/mnt/afs/tj_share/webagent-cci/run/webagent-web.pid
```

Useful checks:

```bash
curl -fsS http://127.0.0.1:8010/api/health
curl -fsS http://127.0.0.1:3000/app
tail -n 120 /mnt/afs/tj_share/webagent-cci/logs/webagent-api.log
tail -n 120 /mnt/afs/tj_share/webagent-cci/logs/webagent-worker.log
tail -n 120 /mnt/afs/tj_share/webagent-cci/logs/webagent-web.log
```

## Troubleshooting

- Login/register `Failed to fetch`: check `NEXT_PUBLIC_API_BASE_URL`, `BACKEND_CORS_ORIGINS`, API port, and SSH tunnel mapping.
- Agent waits without stage bubbles: check worker log first, then API log. Suppressed low-value raw output is still stored as `raw_activity` run events.
- `No such file or directory`: verify `hermes`, `openclaw`, Python runtime, skills paths, and workspace paths in `agent-pack.env`.
- Model 401/invalid token: verify the selected user model config and `agent-pack.env` fallback keys. Per-run model snapshots should be used by adapters.
- Web page stale or old UI: stop with `cci-stop.sh`, remove only `apps/web/.next-build` inside the repo, then start with `cci-start.sh`.
