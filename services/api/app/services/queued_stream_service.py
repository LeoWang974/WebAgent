import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AgentRun, AgentRunEvent, Message
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

    sent_event_ids: set[str] = set()
    assistant_done_sent = False
    run_id = run.id
    while True:
        db.expire_all()
        run = await db.get(AgentRun, run_id)
        if run is None:
            raise RuntimeError("Queued agent run disappeared before completion.")
        result = await db.execute(
            select(AgentRunEvent)
            .where(AgentRunEvent.run_id == run.id)
            .order_by(AgentRunEvent.created_at.asc())
        )
        events = result.scalars().all()
        for event in events:
            if event.id in sent_event_ids:
                continue
            sent_event_ids.add(event.id)
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
                    .where(Message.conversation_id == session_id, Message.role == "assistant")
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
        select(AgentRunEvent).where(
            AgentRunEvent.run_id == run_id,
            AgentRunEvent.event_type == "queued",
        )
    )
    event = result.scalars().first()
    return event.payload if event is not None and isinstance(event.payload, dict) else {}
