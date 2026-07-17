from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
from app.core.security import hash_password
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
from app.services.cleanup_scheduler import run_configured_data_cleanup
from app.services.persistence import (
    get_user_by_email,
    get_user_by_username,
    normalize_email,
    normalize_username,
)

router = APIRouter()

VALID_ROLES = {"admin", "user"}


def to_user_schema(user: User, conversation_count: int = 0) -> schemas.AdminUser:
    return schemas.AdminUser(
        id=user.id,
        nickname=user.nickname,
        email=user.email,
        username=user.username,
        avatar_url=user.avatar_url,
        role=user.role,
        conversation_count=conversation_count,
        created_at=user.created_at.isoformat() if user.created_at else None,
        password_mask="********" if user.hashed_password else "未设置",
        updated_at=user.updated_at.isoformat() if user.updated_at else None,
    )


def require_admin(current_user: User) -> None:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.get("/users", response_model=list[schemas.AdminUser])
async def list_users(
    db: DbSession,
    current_user: CurrentUser,
) -> list[schemas.AdminUser]:
    require_admin(current_user)
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = list(result.scalars().all())
    if not users:
        return []

    count_result = await db.execute(
        select(Conversation.user_id, func.count(Conversation.id))
        .where(Conversation.user_id.in_([user.id for user in users]))
        .group_by(Conversation.user_id)
    )
    conversation_counts = {user_id: count for user_id, count in count_result.all()}
    return [to_user_schema(user, int(conversation_counts.get(user.id, 0))) for user in users]


@router.post("/users", response_model=schemas.AdminUser)
async def create_user(
    input_data: schemas.AdminUserCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.AdminUser:
    require_admin(current_user)
    email = normalize_email(input_data.email)
    if input_data.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if len(input_data.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    if await get_user_by_email(db, email) is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")
    username = normalize_username(input_data.username)
    if username and await get_user_by_username(db, username) is not None:
        raise HTTPException(status_code=409, detail="Username is already registered")

    nickname = (
        input_data.nickname.strip()
        if input_data.nickname and input_data.nickname.strip()
        else email.split("@", 1)[0]
    )
    user = User(
        email=email,
        hashed_password=hash_password(input_data.password),
        nickname=nickname or "user",
        role=input_data.role,
        username=username,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered") from error
    await db.refresh(user)
    return to_user_schema(user)


@router.post("/users/{user_id}/password", response_model=schemas.AdminUser)
async def reset_user_password(
    user_id: str,
    input_data: schemas.AdminPasswordReset,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.AdminUser:
    require_admin(current_user)
    if len(input_data.new_password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(input_data.new_password)
    await db.commit()
    await db.refresh(user)
    conversation_count = await db.scalar(
        select(func.count(Conversation.id)).where(Conversation.user_id == user.id)
    )
    return to_user_schema(user, int(conversation_count or 0))


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    db: DbSession,
    current_user: CurrentUser,
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
        await db.execute(
            delete(ConversationShare).where(ConversationShare.conversation_id.in_(conversation_ids))
        )
        await db.execute(delete(AgentRun).where(AgentRun.conversation_id.in_(conversation_ids)))
        await db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))

    await db.execute(delete(ConversationShare).where(ConversationShare.user_id == user_id))
    await db.execute(delete(ModelConfig).where(ModelConfig.user_id == user_id))
    await db.execute(delete(UserSettings).where(UserSettings.user_id == user_id))
    await db.delete(user)
    await db.commit()
    return None


@router.post("/cleanup")
async def run_cleanup(
    current_user: CurrentUser,
) -> dict[str, int]:
    require_admin(current_user)
    result = await run_configured_data_cleanup()
    return asdict(result)
