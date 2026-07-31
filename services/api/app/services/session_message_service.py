from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.models import Conversation, User
from app.services.persistence import persist_message, to_message, to_session
from app.services.session_artifacts import refresh_conversation


def resolve_skill_key(content: str, explicit_skill_key: str | None) -> str | None:
    del content
    return explicit_skill_key


async def send_message_core(
    db: AsyncSession,
    conversation: Conversation,
    input_data: schemas.MessageCreate,
    current_user: User,
) -> schemas.SendMessageResult:
    session_id = conversation.id
    resolved_skill_key = resolve_skill_key(input_data.content, input_data.skill_key)
    from app.services.session_stream_service import enqueue_agent_run_message

    user_message, run = await enqueue_agent_run_message(
        db,
        session_id,
        input_data,
        current_user,
        resolved_skill_key,
    )
    assistant_message = await persist_message(
        db,
        session_id,
        "assistant",
        f"Agent run queued. Run ID: {run.id}",
    )
    conversation.status = "running"
    await db.commit()
    conversation = await refresh_conversation(db, conversation.id)
    return schemas.SendMessageResult(
        messages=[to_message(user_message), to_message(assistant_message)],
        session=to_session(conversation),
    )
