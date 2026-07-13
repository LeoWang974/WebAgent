from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api.routes.settings import list_user_models, to_model_schema
from app.db.session import get_db
from app.models import User
from app.services.persistence import get_current_user

router = APIRouter()


@router.get("", response_model=list[schemas.ModelConfig])
async def list_models(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[schemas.ModelConfig]:
    models = await list_user_models(db, current_user)
    return [to_model_schema(item) for item in models]
