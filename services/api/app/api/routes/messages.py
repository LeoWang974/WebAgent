from fastapi import APIRouter

from app import schemas
from app.services import mock_store

router = APIRouter()


@router.get("", response_model=list[schemas.Message])
async def list_messages() -> list[schemas.Message]:
    return mock_store.messages

