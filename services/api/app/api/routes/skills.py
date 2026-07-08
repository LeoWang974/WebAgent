from fastapi import APIRouter

from app import schemas
from app.services import mock_store

router = APIRouter()


@router.get("", response_model=list[schemas.Skill])
async def list_skills() -> list[schemas.Skill]:
    return mock_store.skills

