import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.core.config import settings
from app.models import AgentRun, AgentRunEvent, Message, User
from app.services.agent_run_dispatcher import enqueue_agent_run_message
from app.services.agent_runs import AgentRunEventCursor, list_new_run_events
from app.services.persistence import to_message, to_session
from app.services.session_artifacts import refresh_conversation
from app.services.stream_protocol import sse


async def stream_queued_agent_run(
    db: AsyncSession,
    session_id: str,
    user_message: Message,
    run: AgentRun,
):
    from app.services.agent_runs import TERMINAL_RUN_STATUSES

    yield f": {' ' * 2048}\n\n"
    yield sse("user_message", to_message(user_message).model_dump(by_alias=True))
    queued_payload = await _queued_event_payload(db, run.id)
    yield sse(
        "run_started",
        {
            "runId": run.id,
            "sessionId": session_id,
            "status": run.status,
            "progress": run.progress,
            "queueName": queued_payload.get("queueName"),
            "queuePosition": queued_payload.get("queuePosition"),
            "queueReason": queued_payload.get("queueReason"),
        },
    )

    event_cursor = AgentRunEventCursor()
    assistant_done_sent = False
    run_id = run.id
    while True:
        run_result = await db.execute(
            select(AgentRun)
            .where(AgentRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        run = run_result.scalar_one_or_none()
        if run is None:
            raise RuntimeError("Queued agent run disappeared before completion.")
        events = await list_new_run_events(db, run.id, event_cursor)
        for event in events:
            payload = event.payload or {}
            if (
                event.event_type != "queued"
                and payload.get("content")
                and payload.get("messageId")
            ):
                yield sse(
                    "assistant_delta",
                    {
                        "content": payload["content"],
                        "messageId": payload["messageId"],
                        "sessionId": session_id,
                        "runId": run.id,
                    },
                )
            if event.event_type == "artifact_created" and isinstance(payload.get("artifact"), dict):
                yield sse(
                    "artifact_created",
                    {
                        "artifact": payload["artifact"],
                        "messageId": payload.get("messageId"),
                        "sessionId": session_id,
                        "runId": run.id,
                    },
                )
            if event.event_type == "assistant_done":
                done_payload = await build_assistant_done_payload(
                    db,
                    session_id,
                    run,
                    payload,
                )
                yield sse("assistant_done", done_payload)
                assistant_done_sent = True

        if run.status in TERMINAL_RUN_STATUSES:
            if not assistant_done_sent:
                message_result = await db.execute(
                    select(Message)
                    .where(
                        Message.conversation_id == session_id,
                        Message.role == "assistant",
                        Message.created_at >= run.created_at,
                    )
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
                message = message_result.scalar_one_or_none()
                if message is not None:
                    conversation = await refresh_conversation(db, session_id)
                    yield sse(
                        "assistant_done",
                        {
                            "message": to_message(message).model_dump(by_alias=True),
                            "session": to_session(conversation).model_dump(by_alias=True),
                            "runId": run.id,
                            "status": run.status,
                        },
                    )
            break
        yield ": heartbeat\n\n"
        await asyncio.sleep(settings.agent_run_event_poll_interval_seconds)


async def stream_session_message_response(
    db: AsyncSession,
    session_id: str,
    input_data: schemas.MessageCreate,
    current_user: User,
) -> AsyncGenerator[str, None]:
    """Queue an unchanged user message and relay persisted events as SSE."""
    user_message, run = await enqueue_agent_run_message(
        db,
        session_id,
        input_data,
        current_user,
    )
    return stream_queued_agent_run(db, session_id, user_message, run)


async def build_assistant_done_payload(
    db: AsyncSession,
    session_id: str,
    run: AgentRun,
    payload: dict,
) -> dict:
    done_payload = dict(payload)
    if "message" not in done_payload and payload.get("messageId"):
        message = await db.get(Message, payload["messageId"])
        if message is not None:
            done_payload["message"] = to_message(message).model_dump(by_alias=True)
    if "session" not in done_payload:
        conversation = await refresh_conversation(db, session_id)
        done_payload["session"] = to_session(conversation).model_dump(by_alias=True)
    done_payload.setdefault("runId", run.id)
    done_payload.setdefault("status", run.status)
    return done_payload


async def _queued_event_payload(db: AsyncSession, run_id: str) -> dict:
    result = await db.execute(
        select(AgentRunEvent.payload)
        .where(
            AgentRunEvent.run_id == run_id,
            AgentRunEvent.event_type == "queued",
        )
        .order_by(AgentRunEvent.created_at.asc())
        .limit(1)
    )
    payload = result.scalar_one_or_none()
    return payload if isinstance(payload, dict) else {}
