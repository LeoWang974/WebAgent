from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.db.session import get_db
from app.models import User
from app.services.persistence import ensure_user, get_current_user

router = APIRouter()


def to_user_schema(user: User) -> schemas.User:
    return schemas.User(
        id=user.id,
        nickname=user.nickname,
        email=user.email,
        avatar_url=user.avatar_url,
    )


@router.post("/login", response_model=schemas.AuthResult)
async def login(
    input_data: schemas.LoginInput,
    db: AsyncSession = Depends(get_db),
) -> schemas.AuthResult:
    user = await ensure_user(db, input_data.email, input_data.password)
    return schemas.AuthResult(access_token=f"dev_token_{input_data.email}", user=to_user_schema(user))


@router.post("/register", response_model=schemas.AuthResult)
async def register(
    input_data: schemas.LoginInput,
    db: AsyncSession = Depends(get_db),
) -> schemas.AuthResult:
    user = await ensure_user(db, input_data.email, input_data.password)
    return schemas.AuthResult(access_token=f"dev_token_{input_data.email}", user=to_user_schema(user))


@router.post("/logout", status_code=204)
async def logout() -> None:
    return None


@router.get("/me", response_model=schemas.User)
async def me(current_user: User = Depends(get_current_user)) -> schemas.User:
    return to_user_schema(current_user)
