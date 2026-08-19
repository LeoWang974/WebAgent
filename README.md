# WebAgent

WebAgent is a multi-user web interface for the Hermes CLI. The browser only
needs the frontend application port `3000`; Next.js proxies `/api/*` to the
internal FastAPI service on port `8010`.

The web client always uses the real FastAPI path. The former browser-only mock
adapter has been removed so local and deployed builds exercise the same flow.

The runtime boundary is intentionally small:

1. Persist users, conversations, messages, runs, and artifacts.
2. Send the user's message to Hermes without rewriting it or selecting a skill.
3. Convert Hermes runtime feedback into SSE stage messages.
4. Discover, persist, preview, and download files produced by Hermes.

The application does not contain a second agent runtime and does not generate
replacement reports, HTML pages, or PPTX files when Hermes does not produce one.

## Architecture

```text
Browser :3000
    |
    +-- Next.js UI
    |     +-- /api/* reverse proxy
    |
    +-- FastAPI :8010 (internal)
          +-- PostgreSQL: users, sessions, messages, runs, artifacts
          +-- Redis: Celery queues and adapter capacity locks
          +-- Celery workers
                +-- short-chat queue
                +-- agent-runs queue
                      +-- Hermes CLI
```

Only port `3000` is user-facing. Port `8010`, PostgreSQL, and Redis should stay
inside the host or container network.

## Project Structure

```text
apps/web                 Next.js workspace UI
  src/app                Routes and layouts
  src/components         Workspace, settings, admin, and artifact UI
  src/services           FastAPI adapters and SSE parsing
  src/stores             Client state and runtime event handling
services/api             FastAPI service and migrations
  app/api/routes         HTTP and SSE endpoints
  app/integrations/hermes Hermes CLI adapter and protocol parsing
  app/services           Runs, queues, persistence, artifacts, and cleanup
  app/workers            Celery task entry points
  tests                  Backend unit and integration tests
scripts                  Local development and CCI process scripts
docs                     Operations, deployment, and testing notes
```

## Runtime Model

- Hermes is the only Agent runtime.
- Users choose an API configuration for Hermes: provider, base URL, model name,
  and encrypted API key.
- Every Agent Run stores a model configuration snapshot.
- Every run has a user/conversation/run-scoped workspace.
- Short chats use the `short-chat` Celery queue; long jobs use `agent-runs`.
- Queue classification changes scheduling priority only. It never changes the
  prompt sent to Hermes.
- Adapter capacity is scoped per conversation so different users and different
  conversations can run concurrently.

## Local Development

Requirements: Python 3.12, Node.js, pnpm, PostgreSQL, Redis, and Hermes CLI.

```powershell
Copy-Item .env.example .env
pnpm install

cd services/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
cd ../..

powershell -ExecutionPolicy Bypass -File scripts/dev-all.ps1
```

The scripts start:

- Next.js on `0.0.0.0:3000`.
- FastAPI on `127.0.0.1:8010`.
- A Celery worker consuming `short-chat` and `agent-runs`.

Use the following command to stop all three processes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop-dev.ps1
```

Default URLs:

- Web: `http://127.0.0.1:3000/app`
- API health: `http://127.0.0.1:8010/api/health`

The frontend defaults to same-origin API requests. Keep
`NEXT_PUBLIC_API_BASE_URL` empty so Next.js can proxy `/api/*` to FastAPI using
`API_INTERNAL_BASE_URL`.

## Configuration

Use [.env.example](.env.example) for local development and
[.env.production.example](.env.production.example) for deployment. Required
production secrets include:

- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET_KEY`
- `MODEL_CONFIG_ENCRYPTION_KEY`
- a default model API key, unless every user supplies one

Hermes-specific paths:

- `HERMES_CLI_PATH`
- `HERMES_HOME`
- `HERMES_SKILLS_DIR`
- `HERMES_WSL_DISTRIBUTION` on Windows/WSL2

## Skills

The optional scheduler synchronizes
[SenseNova-Skills](https://github.com/OpenSenseNova/SenseNova-Skills) into the
Hermes skills directory. WebAgent does not select a skill for a user message;
Hermes receives the original message and makes that decision itself.

## Source Documentation Convention

First-party Python, TypeScript, JavaScript, CSS, PowerShell, and shell files
start with a concise header containing:

1. `File purpose`: the responsibility and ownership boundary of the file.
2. `Main declarations`: the role of the file's top-level classes and functions.

Keep these headers synchronized when moving responsibilities or renaming public
declarations. Prefer comments that explain ownership and behavior; implementation
details should remain next to the relevant code only when they are not obvious.

## CCI Deployment

CCI uses the persistent directory `/mnt/afs/tj_share/webagent-cci`. After the
runtime and repository have been prepared, the application entry point is:

```bash
#!/usr/bin/env bash
set -euo pipefail

exec /bin/bash \
  /mnt/afs/tj_share/webagent-cci/repo/WebAgent/scripts/cci-app-start.sh
```

Configure the CCI application port and DNAT target as `3000`. The entry script
starts and supervises FastAPI, Celery, PostgreSQL, Redis, Hermes, and Next.js;
only Next.js is exposed through the application port.

## Verification

```powershell
powershell -ExecutionPolicy Bypass -File scripts/test-api.ps1 -Group all
pnpm --dir apps/web test
pnpm --dir apps/web lint
pnpm --dir apps/web build
```

The API health endpoint checks both PostgreSQL and Redis:

```text
GET http://127.0.0.1:8010/api/health
```

See [docs/TESTING.md](docs/TESTING.md) and
[docs/CCI_BARE_METAL.md](docs/CCI_BARE_METAL.md) for detailed checks and CCI
operations.
