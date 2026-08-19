# File purpose: Defines FastAPI endpoints for the messages API surface.
# Main declarations: list_messages lists messages.

from fastapi import APIRouter
from sqlalchemy import or_, select

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
from app.models import Conversation, ConversationShare, Message
from app.services.persistence import to_message

router = APIRouter()


@router.get("", response_model=list[schemas.Message])
async def list_messages(
    db: DbSession,
    current_user: CurrentUser,
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
