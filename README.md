# WebAgent

WebAgent is a multi-user web interface for the Hermes CLI. It keeps the runtime
boundary intentionally small:

1. Persist users, conversations, messages, runs, and artifacts.
2. Send the user's message to Hermes without rewriting it or selecting a skill.
3. Convert Hermes runtime feedback into SSE stage messages.
4. Discover, persist, preview, and download files produced by Hermes.

The application does not contain a second agent runtime and does not generate
replacement reports, HTML pages, or PPTX files when Hermes does not produce one.

## Structure

```text
apps/web                 Next.js workspace UI
services/api             FastAPI, SQLAlchemy, Celery, PostgreSQL, Redis
services/api/app/integrations/hermes   Hermes CLI integration
scripts                  Local and CCI process scripts
docs                     Operations and testing notes
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

Default URLs:

- Web: `http://127.0.0.1:3000/app`
- API health: `http://127.0.0.1:8010/api/health`

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

## Verification

```powershell
powershell -ExecutionPolicy Bypass -File scripts/test-api.ps1 -Group all
pnpm --dir apps/web test
pnpm --dir apps/web build
```

See [docs/TESTING.md](docs/TESTING.md) and
[docs/CCI_BARE_METAL.md](docs/CCI_BARE_METAL.md) for detailed checks and CCI
operations.
