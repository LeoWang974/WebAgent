# File purpose: Implements the session message service backend service workflow.
# Main declarations: send_message_core handles send message core.

from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.models import Conversation, User
from app.services.agent_run_dispatcher import enqueue_agent_run_message
from app.services.persistence import to_message, to_session
from app.services.session_artifacts import refresh_conversation


async def send_message_core(
    db: AsyncSession,
    conversation: Conversation,
    input_data: schemas.MessageCreate,
    current_user: User,
) -> schemas.SendMessageResult:
    session_id = conversation.id
    user_message, run = await enqueue_agent_run_message(
        db,
        session_id,
        input_data,
        current_user,
    )
    conversation = await refresh_conversation(db, conversation.id)
    return schemas.SendMessageResult(
        messages=[to_message(user_message)],
        run_id=run.id,
        session=to_session(conversation),
    )
