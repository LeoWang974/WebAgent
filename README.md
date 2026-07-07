# WebAgent

WebAgent is a full-stack web agent workspace. The initial milestone focuses on a complete frontend shell with mock data, leaving integration points for FastAPI, openclaw/hermes, file rendering, and persistent storage.

## Planned Stack

- Frontend: Next.js, React, TypeScript, Tailwind CSS, shadcn/ui
- Backend: Python FastAPI, SQLAlchemy, Pydantic
- Jobs: RQ or Celery with Redis
- Database: PostgreSQL
- Agent runtime: openclaw or hermes through adapters
- Rendering: Markdown, PPT, image, and data preview services

## Repository Layout

```text
apps/web              Frontend app
services/api          FastAPI backend placeholder
services/agent-runtime Agent runtime adapters and workflows
services/renderer     File rendering service placeholder
packages/shared       Shared frontend types/constants
packages/ui           Future shared UI package
infra                 Docker, nginx, deployment assets
docs                  Product and architecture documents
scripts               Local setup and development scripts
```

