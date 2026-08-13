from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.models import User
from app.services.agent_run_dispatcher import enqueue_agent_run_message
from app.services.queued_stream_service import stream_queued_agent_run


async def stream_session_message_response(
    db: AsyncSession,
    session_id: str,
    input_data: schemas.MessageCreate,
    current_user: User,
) -> AsyncGenerator[str, None]:
    """Queue every message for Hermes and relay persisted events as SSE.

    WebAgent deliberately does not infer skills or rewrite the user's prompt. Queue
    selection may classify a request as short or long for scheduling only; the
    content delivered to Hermes remains ``input_data.content``.
    """

    user_message, run = await enqueue_agent_run_message(
        db,
        session_id,
        input_data,
        current_user,
    )
    return stream_queued_agent_run(db, session_id, user_message, run)
