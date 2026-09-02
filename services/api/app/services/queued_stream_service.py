# File purpose: Implements the queued stream service backend service workflow.
# Main declarations: stream_queued_agent_run handles stream queued agent run;
# stream_session_message_response handles stream session message response;
# build_assistant_done_payload builds assistant done payload; _queued_event_payload handles queued
# event payload.

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
    try:
        # Snapshot ORM-backed values before the first yield. StreamingResponse may
        # roll back the request transaction between iterator advances, which can
        # expire these objects and trigger implicit async ORM IO on resume.
        run_id = run.id
        user_message_payload = to_message(user_message).model_dump(by_alias=True)
        queued_payload = await _queued_event_payload(db, run_id)
        run_started_payload = {
            "runId": run_id,
            "sessionId": session_id,
            "status": run.status,
            "progress": run.progress,
            "queueName": queued_payload.get("queueName"),
            "queuePosition": queued_payload.get("queuePosition"),
            "queueReason": queued_payload.get("queueReason"),
        }
        yield f": {' ' * 2048}\n\n"
        user_message_event = sse("user_message", user_message_payload)
        run_started_event = sse("run_started", run_started_payload)
        await db.rollback()
        yield user_message_event
        yield run_started_event

        event_cursor = AgentRunEventCursor()
        assistant_done_sent = False
        while True:
            run_result = await db.execute(
                select(AgentRun)
                .where(AgentRun.id == run_id)
                .execution_options(populate_existing=True)
            )
            run = run_result.scalar_one_or_none()
            if run is None:
                await db.rollback()
                raise RuntimeError("Queued agent run disappeared before completion.")
            events = await list_new_run_events(db, run.id, event_cursor)
            encoded_events: list[str] = []
            for event in events:
                payload = event.payload or {}
                event_content = payload.get("content")
                if (
                    event.event_type != "queued"
                    and isinstance(event_content, str)
                    and event_content
                ):
                    encoded_events.append(
                        sse(
                            "assistant_delta",
                            {
                                "content": event_content,
                                "messageId": str(
                                    payload.get("messageId") or f"run_event_{run.id}_{event.id}"
                                ),
                                "sessionId": session_id,
                                "runId": run.id,
                            },
                        )
                    )
                if event.event_type == "artifact_created" and isinstance(
                    payload.get("artifact"), dict
                ):
                    encoded_events.append(
                        sse(
                            "artifact_created",
                            {
                                "artifact": payload["artifact"],
                                "messageId": payload.get("messageId"),
                                "sessionId": session_id,
                                "runId": run.id,
                            },
                        )
                    )
                if event.event_type == "assistant_done":
                    encoded_events.append(
                        sse(
                            "assistant_done",
                            await build_assistant_done_payload(
                                db,
                                session_id,
                                run,
                                payload,
                            ),
                        )
                    )
                    assistant_done_sent = True

            is_terminal = run.status in TERMINAL_RUN_STATUSES
            if is_terminal and not assistant_done_sent:
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
                    encoded_events.append(
                        sse(
                            "assistant_done",
                            {
                                "message": to_message(message).model_dump(by_alias=True),
                                "session": to_session(conversation).model_dump(by_alias=True),
                                "runId": run.id,
                                "status": run.status,
                            },
                        )
                    )

            # The request stream must never keep a read transaction open while
            # the client is consuming events or waiting for the next poll.
            await db.rollback()
            for encoded_event in encoded_events:
                yield encoded_event
            if is_terminal:
                break
            yield ": heartbeat\n\n"
            await asyncio.sleep(settings.agent_run_event_poll_interval_seconds)
    finally:
        await db.rollback()


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
