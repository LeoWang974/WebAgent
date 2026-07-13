from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api.routes.settings import list_skill_configs, to_skill_schema
from app.db.session import get_db

router = APIRouter()


@router.get("", response_model=list[schemas.Skill])
async def list_skills(
    db: AsyncSession = Depends(get_db),
) -> list[schemas.Skill]:
    skills = await list_skill_configs(db)
    return [to_skill_schema(item) for item in skills]
