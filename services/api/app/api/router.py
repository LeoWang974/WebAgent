from fastapi import APIRouter

from app.api.routes import (
    admin,
    agent_runs,
    artifacts,
    auth,
    files,
    health,
    messages,
    models,
    sessions,
    settings,
    skills,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(messages.router, prefix="/messages", tags=["messages"])
api_router.include_router(artifacts.router, prefix="/artifacts", tags=["artifacts"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(agent_runs.router, prefix="/agent-runs", tags=["agent-runs"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(skills.router, prefix="/skills", tags=["skills"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
