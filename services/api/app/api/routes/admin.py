from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.core.security import hash_password
from app.db.session import get_db
from app.models import (
    AgentRun,
    AgentRunEvent,
    Artifact,
    Conversation,
    ConversationShare,
    FileAsset,
    Message,
    ModelConfig,
    User,
    UserSettings,
)
from app.services.persistence import get_current_user, get_user_by_email, normalize_email

router = APIRouter()

VALID_ROLES = {"admin", "user"}


def to_user_schema(user: User) -> schemas.User:
    return schemas.User(
        id=user.id,
        nickname=user.nickname,
        email=user.email,
        avatar_url=user.avatar_url,
        role=user.role,
    )


def require_admin(current_user: User) -> None:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.get("/users", response_model=list[schemas.User])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[schemas.User]:
    require_admin(current_user)
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return [to_user_schema(user) for user in result.scalars().all()]


@router.post("/users", response_model=schemas.User)
async def create_user(
    input_data: schemas.AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> schemas.User:
    require_admin(current_user)
    email = normalize_email(input_data.email)
    if input_data.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if len(input_data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if await get_user_by_email(db, email) is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")

    nickname = input_data.nickname.strip() if input_data.nickname and input_data.nickname.strip() else email.split("@", 1)[0]
    user = User(
        email=email,
        hashed_password=hash_password(input_data.password),
        nickname=nickname or "user",
        role=input_data.role,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered") from error
    await db.refresh(user)
    return to_user_schema(user)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    require_admin(current_user)
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    conversation_ids_result = await db.execute(
        select(Conversation.id).where(Conversation.user_id == user_id)
    )
    conversation_ids = list(conversation_ids_result.scalars().all())
    if conversation_ids:
        run_ids_result = await db.execute(
            select(AgentRun.id).where(AgentRun.conversation_id.in_(conversation_ids))
        )
        run_ids = list(run_ids_result.scalars().all())
        if run_ids:
            await db.execute(delete(AgentRunEvent).where(AgentRunEvent.run_id.in_(run_ids)))
        await db.execute(delete(Artifact).where(Artifact.conversation_id.in_(conversation_ids)))
        await db.execute(delete(FileAsset).where(FileAsset.conversation_id.in_(conversation_ids)))
        await db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
        await db.execute(delete(ConversationShare).where(ConversationShare.conversation_id.in_(conversation_ids)))
        await db.execute(delete(AgentRun).where(AgentRun.conversation_id.in_(conversation_ids)))
        await db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))

    await db.execute(delete(ConversationShare).where(ConversationShare.user_id == user_id))
    await db.execute(delete(ModelConfig).where(ModelConfig.user_id == user_id))
    await db.execute(delete(UserSettings).where(UserSettings.user_id == user_id))
    await db.delete(user)
    await db.commit()
    return None
