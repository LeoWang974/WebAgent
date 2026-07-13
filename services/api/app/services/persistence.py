from datetime import datetime

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import schemas
from app.db.session import get_db
from app.models import Artifact, Conversation, ConversationShare, Message, User

DEFAULT_DEV_EMAIL = "demo@webagent.local"


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def extract_dev_email(authorization: str | None) -> str:
    if not authorization:
        return DEFAULT_DEV_EMAIL

    token = authorization.removeprefix("Bearer").strip()
    if token.startswith("dev_token_"):
        return token.removeprefix("dev_token_")
    return DEFAULT_DEV_EMAIL


async def ensure_user(db: AsyncSession, email: str, password: str | None = None) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    nickname = email.split("@", maxsplit=1)[0] or "user"
    user = User(email=email, hashed_password=password, nickname=nickname)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await ensure_user(db, extract_dev_email(authorization))


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
        id=artifact.id,
        session_id=artifact.conversation_id,
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
