import asyncio
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
from app.core.config import settings
from app.models import AgentRun as DBAgentRun
from app.models import AgentRunEvent as DBAgentRunEvent
from app.models import Conversation, ConversationShare, ModelConfig, User
from app.services.persistence import get_conversation_or_404
from app.services.skills_updater import default_openclaw_skills_dir

try:
    from agent_runtime.adapters import HermesAdapter, OpenClawAdapter

    openclaw_skills_dir = settings.openclaw_skills_dir or str(default_openclaw_skills_dir())
    openclaw_adapter = OpenClawAdapter(
        settings.openclaw_base_url,
        agent_id=settings.openclaw_agent_id,
        cli_path=settings.openclaw_cli_path,
        command_timeout_seconds=settings.openclaw_command_timeout_seconds,
        mode=settings.openclaw_mode,
        skills_dir=openclaw_skills_dir,
    )
    hermes_adapter = HermesAdapter(
        hermes_path=settings.hermes_cli_path,
        hermes_home=settings.hermes_home,
        wsl_distribution=settings.hermes_wsl_distribution,
    )
except ImportError:
    openclaw_adapter = None
    hermes_adapter = None

router = APIRouter()
ACTIVE_RUN_STATUSES = {"queued", "running", "tool_calling", "rendering"}
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "disconnected"}
STALE_RUN_GRACE_SECONDS = 30 * 60


def _resolve_adapter(model_id: str | None = None, adapter_key: str | None = None):
    if adapter_key == "hermes":
        return ("hermes", hermes_adapter) if hermes_adapter else (None, None)
    if adapter_key == "openclaw":
        return ("openclaw", openclaw_adapter) if openclaw_adapter else (None, None)
    if model_id == "model_hermes" and hermes_adapter:
        return "hermes", hermes_adapter
    if model_id == "model_openclaw" and openclaw_adapter:
        return "openclaw", openclaw_adapter
    if settings.agent_runtime_default == "openclaw" and openclaw_adapter:
        return "openclaw", openclaw_adapter
    if hermes_adapter:
        return "hermes", hermes_adapter
    if openclaw_adapter:
        return "openclaw", openclaw_adapter
    return None, None


def _infer_adapter_key_from_model(model: ModelConfig | None) -> str | None:
    if model is None:
        return None

    name = (model.name or "").lower()
    provider = (model.provider or "").lower()
    base_url = (model.base_url or "").lower()
    if "openclaw" in name or "openclaw" in base_url or "18789" in base_url:
        return "openclaw"
    if "hermes" in name or "hermes" in base_url or "8642" in base_url:
        return "hermes"
    if provider == "sensenova":
        return settings.agent_runtime_default
    return None


async def resolve_adapter_for_model(
    db: AsyncSession,
    current_user: User,
    model_id: str | None = None,
    adapter_key: str | None = None,
):
    if adapter_key:
        return _resolve_adapter(adapter_key=adapter_key)
    if not model_id:
        return _resolve_adapter(model_id=model_id)

    if model_id in {"model_hermes", "model_openclaw"}:
        return _resolve_adapter(model_id=model_id)

    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == model_id,
            ModelConfig.user_id == current_user.id,
        )
    )
    inferred_adapter_key = _infer_adapter_key_from_model(result.scalar_one_or_none())
    return _resolve_adapter(adapter_key=inferred_adapter_key, model_id=model_id)


def _get_adapter(model_id: str | None):
    return _resolve_adapter(model_id=model_id)[1]


def _event_to_step(event: DBAgentRunEvent) -> schemas.AgentRunStep:
    payload = event.payload or {}
    step_payload = payload.get("step") if isinstance(payload.get("step"), dict) else {}
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
        id=event.id,
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
    for event in reversed(events):
        payload = event.payload or {}
        if payload.get("output"):
            output = str(payload["output"])
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
        run.status = "disconnected"
        run.error = "Agent run disconnected before a terminal status was recorded."
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
                    "step": {
                        "label": "Agent run disconnected",
                        "status": "failed",
                    },
                },
            )
        )
    await db.commit()


async def create_db_agent_run(
    db: AsyncSession,
    session_id: str,
    *,
    title: str,
    status: str = "running",
    progress: int = 0,
    adapter_key: str | None = None,
) -> DBAgentRun:
    run = DBAgentRun(
        conversation_id=session_id,
        status=status,
        title=title,
        progress=progress,
        adapter_key=adapter_key,
    )
    db.add(run)
    await db.commit()
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
) -> DBAgentRunEvent:
    run.status = status or run.status
    if progress is not None:
        run.progress = progress
    event_payload = {
        "eventType": event_type,
        "status": run.status,
        "progress": run.progress,
        "step": {
            "label": label,
            "status": step_status,
        },
        **(payload or {}),
    }
    event = DBAgentRunEvent(run_id=run.id, event_type=event_type, payload=event_payload)
    db.add(event)
    await db.commit()
    await db.refresh(run)
    await db.refresh(event)
    return event


async def finish_db_agent_run(
    db: AsyncSession,
    run: DBAgentRun,
    *,
    status: str,
    label: str,
    error: str | None = None,
    output: str | None = None,
) -> DBAgentRunEvent:
    run.status = status
    run.progress = 100 if status == "completed" else run.progress
    run.error = error
    return await record_db_agent_run_event(
        db,
        run,
        event_type=status,
        label=label,
        status=status,
        progress=run.progress,
        step_status="completed" if status == "completed" else "failed",
        payload={"error": error, "output": output},
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


@router.get("", response_model=list[schemas.AgentRun])
async def list_agent_runs(
    db: DbSession,
    current_user: CurrentUser,
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


@router.post("", response_model=schemas.AgentRun)
async def create_agent_run(
    input_data: schemas.AgentRunCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.AgentRun:
    await get_conversation_or_404(db, input_data.session_id, current_user, require_write=True)
    adapter_key, _ = await resolve_adapter_for_model(db, current_user, input_data.model_id)
    run = await create_db_agent_run(
        db,
        input_data.session_id,
        title=input_data.skill_key or "Agent Run",
        status="queued",
        progress=0,
        adapter_key=adapter_key,
    )
    event = await record_db_agent_run_event(
        db,
        run,
        event_type="queued",
        label="Queued agent run",
        status="queued",
        progress=0,
        step_status="pending",
        payload={
            "content": input_data.content,
            "modelId": input_data.model_id,
            "skillKey": input_data.skill_key,
        },
    )
    return to_agent_run_schema(run, [event])


@router.get("/{run_id}", response_model=schemas.AgentRun)
async def get_agent_run(
    run_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.AgentRun:
    run = await get_db_agent_run(db, run_id, current_user)
    events = await list_run_events(db, run_id)
    return to_agent_run_schema(run, events)


@router.post("/{run_id}/cancel", response_model=schemas.AgentRun)
async def cancel_agent_run(
    run_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.AgentRun:
    run = await get_db_agent_run(db, run_id, current_user)
    await get_conversation_or_404(db, run.conversation_id, current_user, require_write=True)
    _, adapter = await resolve_adapter_for_model(db, current_user, adapter_key=run.adapter_key)
    adapter_cancelled = False
    adapter_error = None
    if adapter is not None:
        try:
            await adapter.cancel_run(run_id)
            adapter_cancelled = True
        except Exception as error:
            adapter_error = str(error)
    event = await finish_db_agent_run(
        db,
        run,
        status="cancelled",
        label="Agent run cancelled",
    )
    event.payload = {
        **(event.payload or {}),
        "adapterKey": run.adapter_key,
        "adapterCancelled": adapter_cancelled,
        "adapterError": adapter_error,
    }
    await db.commit()
    await db.refresh(event)
    events = await list_run_events(db, run_id)
    if event not in events:
        events.append(event)
    return to_agent_run_schema(run, events)


@router.get("/{run_id}/events")
async def stream_agent_run_events(
    run_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> StreamingResponse:
    await get_db_agent_run(db, run_id, current_user)

    async def event_stream():
        sent_event_ids: set[str] = set()
        while True:
            run = await get_db_agent_run(db, run_id, current_user)
            events = await list_run_events(db, run_id)
            for event in events:
                if event.id in sent_event_ids:
                    continue
                sent_event_ids.add(event.id)
                api_event = to_agent_run_event_schema(event, run)
                event_data = json.dumps(
                    api_event.model_dump(by_alias=True),
                    ensure_ascii=False,
                )
                yield (
                    "event: agent_run_event\n"
                    f"data: {event_data}\n\n"
                )
            if run.status in TERMINAL_RUN_STATUSES:
                break
            yield ": heartbeat\n\n"
            await asyncio.sleep(settings.agent_run_event_poll_interval_seconds)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
