from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import User
from app.services.persistence import ensure_user, get_current_user, get_user_by_email, normalize_email

router = APIRouter()


def to_user_schema(user: User) -> schemas.User:
    return schemas.User(
        id=user.id,
        nickname=user.nickname,
        email=user.email,
        avatar_url=user.avatar_url,
        role=user.role,
    )


@router.post("/login", response_model=schemas.AuthResult)
async def login(
    input_data: schemas.LoginInput,
    db: AsyncSession = Depends(get_db),
) -> schemas.AuthResult:
    if len(input_data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user = await get_user_by_email(db, input_data.email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    password_matches = verify_password(input_data.password, user.hashed_password)
    if not password_matches and user.hashed_password == input_data.password:
        user.hashed_password = hash_password(input_data.password)
        await db.commit()
        await db.refresh(user)
        password_matches = True

    if not password_matches:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    return schemas.AuthResult(access_token=create_access_token(user.id), user=to_user_schema(user))


@router.post("/register", response_model=schemas.AuthResult)
async def register(
    input_data: schemas.RegisterInput,
    db: AsyncSession = Depends(get_db),
) -> schemas.AuthResult:
    if len(input_data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    if await get_user_by_email(db, input_data.email) is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")

    try:
        user = await ensure_user(
            db,
            normalize_email(input_data.email),
            input_data.password,
            input_data.nickname,
        )
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered") from error

    return schemas.AuthResult(access_token=create_access_token(user.id), user=to_user_schema(user))


@router.post("/logout", status_code=204)
async def logout() -> None:
    return None


@router.get("/me", response_model=schemas.User)
async def me(current_user: User = Depends(get_current_user)) -> schemas.User:
    return to_user_schema(current_user)
