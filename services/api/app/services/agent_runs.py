from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.core.config import settings
from app.integrations.hermes import HermesAdapter
from app.models import AgentRun as DBAgentRun
from app.models import AgentRunEvent as DBAgentRunEvent
from app.models import Conversation, ConversationShare, User
from app.services.model_runtime_config import ModelRuntimeConfig
from app.services.persistence import get_conversation_or_404
from app.services.runtime_environment import build_user_runtime_context

ACTIVE_RUN_STATUSES = {"queued", "running", "tool_calling", "rendering"}
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "disconnected"}
STALE_RUN_GRACE_SECONDS = 30 * 60


@dataclass
class AgentRunEventCursor:
    created_at: datetime | None = None
    event_ids_at_timestamp: set[str] = field(default_factory=set)

    def consume(self, events: list[DBAgentRunEvent]) -> list[DBAgentRunEvent]:
        unseen = [
            event
            for event in events
            if self.created_at is None
            or event.created_at > self.created_at
            or event.id not in self.event_ids_at_timestamp
        ]
        if not events:
            return unseen

        latest_timestamp = events[-1].created_at
        latest_ids = {
            event.id for event in events if event.created_at == latest_timestamp
        }
        if self.created_at == latest_timestamp:
            latest_ids.update(self.event_ids_at_timestamp)
        self.created_at = latest_timestamp
        self.event_ids_at_timestamp = latest_ids
        return unseen


def create_hermes_adapter(
    current_user: User,
    conversation_id: str | None = None,
    run_id: str | None = None,
    model_runtime_config: ModelRuntimeConfig | None = None,
):
    runtime_context = build_user_runtime_context(
        current_user,
        conversation_id,
        run_id=run_id,
        model_runtime_config=model_runtime_config,
    )
    return HermesAdapter(
        hermes_path=settings.hermes_cli_path,
        hermes_home=runtime_context.hermes_home_for_shell(),
        wsl_distribution=settings.hermes_wsl_distribution,
        serper_configured=bool(settings.serper_api_key),
        resume_session_id=runtime_context.hermes_resume_session_id,
    )


def _event_to_step(event: DBAgentRunEvent) -> schemas.AgentRunStep:
    payload = event.payload or {}
    step_payload = payload.get("step") if isinstance(payload.get("step"), dict) else {}
    message_id = payload.get("messageId")
    label = (
        step_payload.get("label")
        or payload.get("content")
        or payload.get("eventType")
        or "Agent event"
    )
    status = step_payload.get("status") or payload.get("stepStatus") or "completed"
    if status not in {"pending", "running", "completed", "failed"}:
        status = "completed"
    return schemas.AgentRunStep(
        id=str(message_id) if isinstance(message_id, str) and message_id else event.id,
        label=str(label),
        status=status,
        timestamp=event.created_at.isoformat(),
    )


def to_agent_run_schema(
    run: DBAgentRun, events: list[DBAgentRunEvent] | None = None
) -> schemas.AgentRun:
    events = events or []
    completed_at = run.updated_at.isoformat() if run.status in TERMINAL_RUN_STATUSES else None
    output = None
    queue_payload = {}
    for event in reversed(events):
        payload = event.payload or {}
        if payload.get("output"):
            output = str(payload["output"])
            break
    for event in events:
        if event.event_type == "queued" and isinstance(event.payload, dict):
            queue_payload = event.payload
            break
    return schemas.AgentRun(
        id=run.id,
        session_id=run.conversation_id,
        status=run.status,
        title=run.title,
        progress=run.progress,
        steps=[_event_to_step(event) for event in events],
        started_at=run.created_at.isoformat(),
        completed_at=completed_at,
        error=run.error,
        output=output,
        adapter_key=run.adapter_key,
        model_config_id=run.model_config_id,
        model_provider=run.model_provider,
        model_name=run.model_name,
        model_base_url=run.model_base_url,
        queue_name=queue_payload.get("queueName"),
        queue_position=queue_payload.get("queuePosition"),
        queue_reason=queue_payload.get("queueReason"),
    )


def to_agent_run_event_schema(event: DBAgentRunEvent, run: DBAgentRun) -> schemas.AgentRunEvent:
    payload = event.payload or {}
    return schemas.AgentRunEvent(
        run_id=run.id,
        event_type=event.event_type,
        status=payload.get("status") or run.status,
        progress=int(payload.get("progress") or run.progress or 0),
        payload=payload,
        completed_at=(
            run.updated_at.isoformat()
            if (payload.get("status") or run.status) in TERMINAL_RUN_STATUSES
            else None
        ),
        error=payload.get("error") or run.error,
        output=payload.get("output"),
        step=_event_to_step(event),
    )


async def list_run_events(db: AsyncSession, run_id: str) -> list[DBAgentRunEvent]:
    result = await db.execute(
        select(DBAgentRunEvent)
        .where(DBAgentRunEvent.run_id == run_id)
        .order_by(DBAgentRunEvent.created_at.asc())
    )
    return list(result.scalars().all())


async def list_new_run_events(
    db: AsyncSession,
    run_id: str,
    cursor: AgentRunEventCursor,
) -> list[DBAgentRunEvent]:
    query = select(DBAgentRunEvent).where(DBAgentRunEvent.run_id == run_id)
    if cursor.created_at is not None:
        same_timestamp = DBAgentRunEvent.created_at == cursor.created_at
        if cursor.event_ids_at_timestamp:
            same_timestamp = and_(
                same_timestamp,
                DBAgentRunEvent.id.not_in(cursor.event_ids_at_timestamp),
            )
        query = query.where(
            or_(
                DBAgentRunEvent.created_at > cursor.created_at,
                same_timestamp,
            )
        )
    result = await db.execute(
        query.order_by(DBAgentRunEvent.created_at.asc(), DBAgentRunEvent.id.asc())
    )
    return cursor.consume(list(result.scalars().all()))


def is_stale_run(run: DBAgentRun) -> bool:
    if run.status not in ACTIVE_RUN_STATUSES:
        return False
    updated_at = run.updated_at or run.created_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return updated_at < datetime.now(UTC) - timedelta(seconds=STALE_RUN_GRACE_SECONDS)


async def mark_stale_agent_runs(
    db: AsyncSession,
    current_user: User,
    session_id: str | None = None,
) -> None:
    conversation_filter = [
        or_(
            Conversation.user_id == current_user.id,
            Conversation.visibility == "public",
            Conversation.id.in_(
                select(ConversationShare.conversation_id).where(
                    ConversationShare.user_id == current_user.id
                )
            ),
        )
    ]
    if session_id:
        conversation_filter.append(Conversation.id == session_id)

    result = await db.execute(
        select(DBAgentRun)
        .join(Conversation, Conversation.id == DBAgentRun.conversation_id)
        .where(
            DBAgentRun.status.in_(ACTIVE_RUN_STATUSES),
            *conversation_filter,
        )
    )
    stale_runs = [run for run in result.scalars().all() if is_stale_run(run)]
    if not stale_runs:
        return

    for run in stale_runs:
        latest_event = await _latest_run_event(db, run.id)
        latest_payload = latest_event.payload if latest_event is not None else {}
        latest_step = latest_payload.get("step") if isinstance(latest_payload, dict) else {}
        latest_label = (
            latest_step.get("label")
            if isinstance(latest_step, dict)
            else None
        )
        raw_log_path = (
            latest_payload.get("rawLogPath")
            if isinstance(latest_payload, dict)
            else None
        )
        runtime_diagnostics = (
            latest_payload.get("runtimeDiagnostics")
            if isinstance(latest_payload, dict)
            else None
        )
        stdout_tail = (
            latest_payload.get("stdoutTail")
            if isinstance(latest_payload, dict)
            else None
        )
        stderr_tail = (
            latest_payload.get("stderrTail")
            if isinstance(latest_payload, dict)
            else None
        )
        run.status = "disconnected"
        run.error = (
            "Agent run disconnected before a terminal status was recorded. "
            f"Last stage: {latest_label or 'unknown'}"
        )
        run.progress = min(run.progress or 0, 99)
        db.add(
            DBAgentRunEvent(
                run_id=run.id,
                event_type="disconnected",
                payload={
                    "eventType": "disconnected",
                    "status": "disconnected",
                    "progress": run.progress,
                    "error": run.error,
                    "diagnosticType": "stale_run",
                    "lastEventType": latest_event.event_type if latest_event else None,
                    "lastEventAt": (
                        latest_event.created_at.isoformat() if latest_event else None
                    ),
                    "lastStage": latest_label,
                    "rawLogPath": raw_log_path,
                    "runtimeDiagnostics": runtime_diagnostics,
                    "stdoutTail": stdout_tail,
                    "stderrTail": stderr_tail,
                    "step": {
                        "label": (
                            "Agent run disconnected"
                            if not latest_label
                            else f"Agent run disconnected after: {latest_label}"
                        ),
                        "status": "failed",
                    },
                },
            )
        )
    await db.commit()


async def _latest_run_event(db: AsyncSession, run_id: str) -> DBAgentRunEvent | None:
    result = await db.execute(
        select(DBAgentRunEvent)
        .where(DBAgentRunEvent.run_id == run_id)
        .order_by(DBAgentRunEvent.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_db_agent_run(
    db: AsyncSession,
    session_id: str,
    *,
    title: str,
    status: str = "running",
    progress: int = 0,
    adapter_key: str | None = None,
    model_runtime_config: ModelRuntimeConfig | None = None,
    commit: bool = True,
) -> DBAgentRun:
    model_snapshot = model_runtime_config.snapshot() if model_runtime_config is not None else {}
    run = DBAgentRun(
        conversation_id=session_id,
        status=status,
        title=title,
        progress=progress,
        adapter_key=adapter_key,
        **model_snapshot,
    )
    db.add(run)
    if commit:
        await db.commit()
    else:
        await db.flush()
    await db.refresh(run)
    return run


async def record_db_agent_run_event(
    db: AsyncSession,
    run: DBAgentRun,
    *,
    event_type: str,
    label: str,
    status: str | None = None,
    progress: int | None = None,
    step_status: str = "completed",
    payload: dict | None = None,
    _refresh_run: bool = True,
    commit: bool = True,
) -> DBAgentRunEvent:
    if _refresh_run:
        await db.refresh(run)
    if run.status == "completed" and status != "completed":
        status = run.status
        progress = run.progress
    elif (
        run.status in TERMINAL_RUN_STATUSES
        and status != run.status
        and not (run.status == "cancelled" and status == "completed")
    ):
        status = run.status
        progress = run.progress
    run.status = status or run.status
    if progress is not None:
        run.progress = progress
    run.updated_at = datetime.now(UTC)
    event_payload = {
        **(payload or {}),
        "eventType": event_type,
        "status": run.status,
        "progress": run.progress,
        "step": {
            "label": label,
            "status": step_status,
        },
    }
    event = DBAgentRunEvent(run_id=run.id, event_type=event_type, payload=event_payload)
    db.add(event)
    if commit:
        await db.commit()
        await db.refresh(run)
        await db.refresh(event)
    else:
        await db.flush()
    return event


async def touch_db_agent_run(
    db: AsyncSession,
    run: DBAgentRun,
    *,
    progress: int | None = None,
) -> None:
    """Refresh an active run heartbeat without adding a low-value event row."""
    await db.refresh(run)
    if run.status not in ACTIVE_RUN_STATUSES:
        return
    run.updated_at = datetime.now(UTC)
    if progress is not None:
        run.progress = max(run.progress, progress)
    await db.commit()
    await db.refresh(run)


async def finish_db_agent_run(
    db: AsyncSession,
    run: DBAgentRun,
    *,
    status: str,
    label: str,
    error: str | None = None,
    output: str | None = None,
) -> DBAgentRunEvent:
    await db.refresh(run)
    requested_status = status
    if run.status == "completed" and status != "completed":
        status = run.status
    elif (
        run.status in TERMINAL_RUN_STATUSES
        and status != run.status
        and not (run.status == "cancelled" and status == "completed")
    ):
        status = run.status

    transition_ignored = status != requested_status
    if status == "completed":
        run.progress = 100
        run.error = None
    elif status == requested_status:
        run.error = error
    return await record_db_agent_run_event(
        db,
        run,
        event_type="terminal_transition_ignored" if transition_ignored else status,
        label=(
            f"Ignored terminal transition to {requested_status}; run remains {status}"
            if transition_ignored
            else label
        ),
        status=status,
        progress=run.progress,
        step_status="completed" if status == "completed" else "failed",
        payload={
            "error": run.error,
            "output": output,
            "requestedStatus": requested_status,
            "transitionIgnored": transition_ignored,
        },
        _refresh_run=False,
    )


async def get_db_agent_run(
    db: AsyncSession,
    run_id: str,
    current_user: User,
) -> DBAgentRun:
    result = await db.execute(select(DBAgentRun).where(DBAgentRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    await get_conversation_or_404(db, run.conversation_id, current_user)
    if is_stale_run(run):
        await mark_stale_agent_runs(db, current_user, run.conversation_id)
        await db.refresh(run)
    return run


async def list_agent_runs_for_user(
    db: AsyncSession,
    current_user: User,
    session_id: str | None = None,
) -> list[schemas.AgentRun]:
    if session_id:
        await get_conversation_or_404(db, session_id, current_user)
    await mark_stale_agent_runs(db, current_user, session_id)

    conversation_filter = [
        or_(
            Conversation.user_id == current_user.id,
            Conversation.visibility == "public",
            Conversation.id.in_(
                select(ConversationShare.conversation_id).where(
                    ConversationShare.user_id == current_user.id
                )
            ),
        )
    ]
    if session_id:
        conversation_filter.append(Conversation.id == session_id)

    result = await db.execute(
        select(DBAgentRun)
        .join(Conversation, Conversation.id == DBAgentRun.conversation_id)
        .where(*conversation_filter)
        .order_by(DBAgentRun.updated_at.desc())
        .limit(50)
    )
    runs = list(result.scalars().all())
    if not runs:
        return []

    events_result = await db.execute(
        select(DBAgentRunEvent)
        .where(DBAgentRunEvent.run_id.in_([run.id for run in runs]))
        .order_by(DBAgentRunEvent.created_at.asc())
    )
    events_by_run: dict[str, list[DBAgentRunEvent]] = {}
    for event in events_result.scalars().all():
        events_by_run.setdefault(event.run_id, []).append(event)
    return [to_agent_run_schema(run, events_by_run.get(run.id, [])) for run in runs]
