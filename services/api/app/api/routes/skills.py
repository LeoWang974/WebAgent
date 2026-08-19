# File purpose: Defines FastAPI endpoints for the skills API surface.
# Main declarations: list_skills lists skills.

from fastapi import APIRouter

from app import schemas
from app.api.dependencies import DbSession
from app.services.settings_service import list_skill_configs, to_skill_schema

router = APIRouter()


@router.get("", response_model=list[schemas.Skill])
async def list_skills(
    db: DbSession,
) -> list[schemas.Skill]:
    skills = await list_skill_configs(db)
    return [to_skill_schema(item) for item in skills]
