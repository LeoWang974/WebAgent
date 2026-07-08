# API Service

FastAPI backend skeleton for WebAgent.

## Local setup

```powershell
cd D:\gitWorkSpace\WebAgent\services\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Start dependencies from the repo root:

```powershell
docker compose -f infra\docker-compose.yml up -d
```

Run the API:

```powershell
uvicorn app.main:app --reload --port 8000
```

Run the worker:

```powershell
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

## Current scope

- FastAPI app entrypoint and CORS
- Pydantic schemas aligned with the frontend adapter contract
- Mock API routes for auth, sessions, messages, artifacts, files, agent runs, models, skills, and settings
- SSE mock endpoint for agent run progress
- SQLAlchemy model skeleton for the MVP tables
- Alembic migration scaffold
- Celery worker scaffold backed by Redis

## Next backend step

Replace `app.services.mock_store` with SQLAlchemy repositories and create the first Alembic migration.
