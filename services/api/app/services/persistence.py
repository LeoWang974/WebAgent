from datetime import datetime

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import schemas
from app.core.config import settings
from app.core.security import decode_access_token, hash_password
from app.db.session import get_db
from app.models import Artifact, Conversation, ConversationShare, Message, User

DEFAULT_DEV_EMAIL = "demo@webagent.local"


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_username(username: str | None) -> str | None:
    value = (username or "").strip().lower()
    return value or None


async def ensure_user(
    db: AsyncSession,
    email: str,
    password: str | None = None,
    nickname: str | None = None,
    role: str = "user",
    username: str | None = None,
) -> User:
    email = normalize_email(email)
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        normalized_username = normalize_username(username)
        if normalized_username and not user.username:
            user.username = normalized_username
            await db.commit()
            await db.refresh(user)
        return user

    display_name = nickname.strip() if nickname and nickname.strip() else email.split("@", maxsplit=1)[0]
    user = User(
        email=email,
        hashed_password=hash_password(password) if password else None,
        nickname=display_name or "user",
        role=role,
        username=normalize_username(username),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == normalize_email(email)))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str | None) -> User | None:
    normalized_username = normalize_username(username)
    if not normalized_username:
        return None
    result = await db.execute(select(User).where(User.username == normalized_username))
    return result.scalar_one_or_none()


async def get_user_by_identifier(db: AsyncSession, identifier: str | None) -> User | None:
    value = (identifier or "").strip()
    if not value:
        return None
    if "@" in value:
        return await get_user_by_email(db, value)
    return await get_user_by_username(db, value)


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_current_user(
    authorization: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = access_token
    if authorization:
        token = authorization.removeprefix("Bearer").strip()

    if token:
        if token.startswith("dev_token_") and settings.allow_dev_auth_fallback:
            return await ensure_user(db, token.removeprefix("dev_token_"))

        user_id = decode_access_token(token)
        if user_id:
            user = await get_user_by_id(db, user_id)
            if user is not None:
                return user

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    if settings.allow_dev_auth_fallback:
        return await ensure_user(db, DEFAULT_DEV_EMAIL)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


def to_session(conversation: Conversation) -> schemas.Session:
    shares = []
    if conversation.visibility == "shared":
        shares = [
            schemas.SessionShare(
                id=share.user.id,
                email=share.user.email,
                nickname=share.user.nickname,
                role=share.role,
            )
            for share in conversation.shares
            if share.user is not None
        ]
    return schemas.Session(
        id=conversation.id,
        owner_id=conversation.user_id,
        title=conversation.title,
        type=conversation.type,
        pinned=conversation.pinned,
        status=conversation.status,
        updated_at=conversation.updated_at.isoformat(),
        visibility=conversation.visibility,
        shared_with=shares,
    )


def to_message(message: Message) -> schemas.Message:
    return schemas.Message(
        id=message.id,
        session_id=message.conversation_id,
        role=message.role,
        content=message.content,
        created_at=message.created_at.isoformat(),
        artifact_ids=message.artifact_ids,
    )


def to_artifact(artifact: Artifact) -> schemas.Artifact:
    return schemas.Artifact(
        created_at=artifact.created_at.isoformat(),
        id=artifact.id,
        session_id=artifact.conversation_id,
        run_id=artifact.run_id,
        type=artifact.type,
        title=artifact.title,
        status=artifact.status,
        content=artifact.content,
        metadata=artifact.artifact_metadata,
    )


async def get_conversation_or_404(
    db: AsyncSession,
    session_id: str,
    current_user: User,
    *,
    require_write: bool = False,
) -> Conversation:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == session_id)
        .options(selectinload(Conversation.shares).selectinload(ConversationShare.user))
        .execution_options(populate_existing=True)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Session not found")

    share = next(
        (item for item in conversation.shares if item.user_id == current_user.id),
        None,
    )
    can_read = (
        conversation.user_id == current_user.id
        or current_user.role == "admin"
        or conversation.visibility == "public"
        or (conversation.visibility == "shared" and share is not None)
    )
    can_write = (
        conversation.user_id == current_user.id
        or (conversation.visibility == "shared" and share is not None)
    )

    if require_write and not can_write:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No write access")
    if not can_read:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return conversation


def require_owner(conversation: Conversation, current_user: User) -> None:
    if conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")
