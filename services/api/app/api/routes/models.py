from fastapi import APIRouter

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
from app.services.settings_service import list_user_models, to_model_schema

router = APIRouter()


@router.get("", response_model=list[schemas.ModelConfig])
async def list_models(
    db: DbSession,
    current_user: CurrentUser,
) -> list[schemas.ModelConfig]:
    models = await list_user_models(db, current_user)
    return [to_model_schema(item) for item in models]
