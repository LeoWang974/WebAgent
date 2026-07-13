from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.db.session import get_db
from app.models import Conversation, ConversationShare, Message, User
from app.services.persistence import get_current_user, to_message

router = APIRouter()


@router.get("", response_model=list[schemas.Message])
async def list_messages(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[schemas.Message]:
    result = await db.execute(
        select(Message)
        .join(Conversation)
        .outerjoin(ConversationShare, ConversationShare.conversation_id == Conversation.id)
        .where(
            or_(
                Conversation.user_id == current_user.id,
                Conversation.visibility == "public",
                (Conversation.visibility == "shared")
                & (ConversationShare.user_id == current_user.id),
            )
        )
        .order_by(Message.created_at.asc())
    )
    return [to_message(item) for item in result.scalars().unique().all()]
