# API Service

FastAPI backend for WebAgent.

## Local setup

```powershell
cd D:\gitWorkSpace\WebAgent\services\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Start PostgreSQL and Redis with your local service manager, then verify the
database URL and Redis URL in `.env`. The current project no longer uses Docker
as a development or CCI deployment path.

```powershell
alembic upgrade head
```

Run the API:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Run the worker:

```powershell
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

## Current scope

- FastAPI app entrypoint and CORS
- Pydantic schemas aligned with the frontend adapter contract
- Database-backed routes for auth, sessions, messages, artifacts, files, agent runs, models, skills, settings, folders, and admin users
- SSE endpoint for queued and direct agent run progress
- SQLAlchemy models and Alembic migrations for the current core tables
- Celery worker scaffold backed by Redis
- Scheduled SenseNova skills updater for Hermes
