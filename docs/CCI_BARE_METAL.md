# CCI Bare-Metal Runbook

WebAgent runs as host processes on CCI. `scripts/cci-start.sh` is the only start
entry point; Docker and OpenClaw are not part of this deployment.

## Directory Contract

The default root is `/mnt/afs/tj_share/webagent-cci`. Override it with
`WEBAGENT_ROOT` when the persistent volume uses another path.

```text
$WEBAGENT_ROOT/
  repo/WebAgent/
  runtime/conda-webagent/bin/python
  runtime/agent-home/.local/bin/hermes
  runtime/agent-home/.hermes/
  logs/
  run/
  secrets/agent-pack.env
  secrets/model-config.key
```

Required services and tools:

- Python runtime at `$WEBAGENT_ROOT/runtime/conda-webagent/bin/python`
- Node.js and pnpm on `PATH`
- PostgreSQL from `DATABASE_URL`
- Redis from `REDIS_URL`
- Hermes CLI on `PATH`
- LibreOffice Impress on `PATH` for browser previews of standalone PPTX files

By default, `scripts/cci-start.sh` starts the user-space PostgreSQL and
Redis/Valkey binaries under `$WEBAGENT_ROOT/runtime/conda-webagent`. Set
`CCI_MANAGE_LOCAL_INFRA=false` when `DATABASE_URL` and `REDIS_URL` point to
externally managed services.

On Ubuntu, install the PPTX renderer with:

```bash
sudo apt-get update
sudo apt-get install -y libreoffice-impress fonts-noto-cjk
```

If LibreOffice is installed outside `PATH`, set `LIBREOFFICE_PATH` to its
`soffice` executable. WebAgent converts PPTX to cached slide images; the
original PPTX remains unchanged and is still used for downloads.

## Environment

Create `$WEBAGENT_ROOT/secrets/agent-pack.env`:

```bash
DATABASE_URL=postgresql+asyncpg://webagent:password@127.0.0.1:5432/webagent
REDIS_URL=redis://127.0.0.1:6379/0
JWT_SECRET_KEY=replace-with-a-long-random-secret

SENSENOVA_API_KEY=sk-...
SENSENOVA_BASE_URL=https://token.sensenova.cn/v1
# Optional PEM bundle when the host/proxy uses a private CA.
SENSENOVA_CA_BUNDLE=
SENSENOVA_TIMEOUT_SECONDS=30
SERPER_API_KEY=...

HERMES_CLI_PATH=$WEBAGENT_ROOT/runtime/agent-home/.local/bin/hermes
HERMES_HOME=$WEBAGENT_ROOT/runtime/agent-home/.hermes
HERMES_SKILLS_DIR=$WEBAGENT_ROOT/runtime/agent-home/.hermes/skills

ARTIFACT_STORAGE_ENABLED=true
ARTIFACT_STORAGE_ROOT=/mnt/afs/tj_share/webagent-cci/artifacts
ARTIFACT_PREVIEW_CACHE_ROOT=$WEBAGENT_ROOT/runtime/artifact-previews
LIBREOFFICE_PATH=/usr/bin/soffice

AGENT_RUN_QUEUE_ENABLED=true
WORKER_INSTANCES=4
BACKEND_CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
```

Do not commit real keys. Preserve `secrets/model-config.key`; historical user
model credentials cannot be decrypted without it.

If the SenseNova connection reports `CERTIFICATE_VERIFY_FAILED`, export the
complete PEM certificate chain trusted by the host/proxy and set
`SENSENOVA_CA_BUNDLE` to that file. The same bundle is passed to the Hermes
runtime as `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE`; TLS verification remains
enabled.

`scripts/cci-start.sh` defaults `ARTIFACT_STORAGE_ROOT` to `$WEBAGENT_ROOT/artifacts` and creates
the directory before migrations and workers start. On the current CCI deployment,
`WEBAGENT_ROOT=/mnt/afs/tj_share/webagent-cci`, so original artifacts and both manifest files remain
on AFS across application restarts.

## Operations

```bash
cd "$WEBAGENT_ROOT/repo/WebAgent"
WEB_PORT=3000 API_PORT=8010 bash scripts/cci-start.sh
bash scripts/cci-status.sh
bash scripts/cci-stop.sh
```

The start script launches FastAPI, six content-agnostic Agent Run workers, and
Next.js. It also runs Alembic migrations before accepting requests. WebAgent
does not classify user prompts; every message is forwarded unchanged to Hermes.

Useful checks:

```bash
curl -fsS http://127.0.0.1:8010/api/health
curl -fsS http://127.0.0.1:3000/app
command -v hermes
redis-cli ping
pg_isready
tail -n 120 "$WEBAGENT_ROOT/logs/webagent-api.log"
tail -n 120 "$WEBAGENT_ROOT/logs/webagent-worker-1.log"
tail -n 120 "$WEBAGENT_ROOT/logs/webagent-web.log"
```

If a run stalls, inspect the worker log, the Agent Run event list, and the
run-scoped workspace under `$WEBAGENT_ROOT/runtime/users`. Do not delete another
user's runtime directory while workers are running.
