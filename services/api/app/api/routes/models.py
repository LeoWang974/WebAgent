from fastapi import APIRouter

from app import schemas
from app.services import mock_store

router = APIRouter()


@router.get("", response_model=list[schemas.ModelConfig])
async def list_models() -> list[schemas.ModelConfig]:
    return mock_store.models

