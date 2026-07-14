import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.core.config import settings
from app.db.session import get_db
from app.models import AgentRun as DBAgentRun
from app.models import AgentRunEvent as DBAgentRunEvent
from app.models import User
from app.services.persistence import get_conversation_or_404, get_current_user

try:
    from agent_runtime.adapters import HermesAdapter, OpenClawAdapter

    openclaw_adapter = OpenClawAdapter(settings.openclaw_base_url)
    hermes_adapter = HermesAdapter(
        hermes_path=settings.hermes_cli_path,
        hermes_home=settings.hermes_home,
        wsl_distribution=settings.hermes_wsl_distribution,
    )
except ImportError:
    openclaw_adapter = None
    hermes_adapter = None

router = APIRouter()


def _get_adapter(model_id: str | None):
    if model_id == "model_hermes" and hermes_adapter:
        return hermes_adapter
    if model_id == "model_openclaw" and openclaw_adapter:
        return openclaw_adapter
    if settings.agent_runtime_default == "openclaw" and openclaw_adapter:
        return openclaw_adapter
    if hermes_adapter:
        return hermes_adapter
    if openclaw_adapter:
        return openclaw_adapter
    return None


def _event_to_step(event: DBAgentRunEvent) -> schemas.AgentRunStep:
    payload = event.payload or {}
    step_payload = payload.get("step") if isinstance(payload.get("step"), dict) else {}
    label = step_payload.get("label") or payload.get("content") or payload.get("eventType") or "Agent event"
    status = step_payload.get("status") or payload.get("stepStatus") or "completed"
    if status not in {"pending", "running", "completed", "failed"}:
        status = "completed"
    return schemas.AgentRunStep(
        id=event.id,
        label=str(label),
        status=status,
        timestamp=event.created_at.isoformat(),
    )


def to_agent_run_schema(run: DBAgentRun, events: list[DBAgentRunEvent] | None = None) -> schemas.AgentRun:
    events = events or []
    completed_at = run.updated_at.isoformat() if run.status in {"completed", "failed", "cancelled"} else None
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
    )


def to_agent_run_event_schema(event: DBAgentRunEvent, run: DBAgentRun) -> schemas.AgentRunEvent:
    payload = event.payload or {}
    return schemas.AgentRunEvent(
        run_id=run.id,
        status=payload.get("status") or run.status,
        progress=int(payload.get("progress") or run.progress or 0),
        completed_at=(
            run.updated_at.isoformat()
            if (payload.get("status") or run.status) in {"completed", "failed", "cancelled"}
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


async def create_db_agent_run(
    db: AsyncSession,
    session_id: str,
    *,
    title: str,
    status: str = "running",
    progress: int = 0,
) -> DBAgentRun:
    run = DBAgentRun(
        conversation_id=session_id,
        status=status,
        title=title,
        progress=progress,
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
    return run


@router.post("", response_model=schemas.AgentRun)
async def create_agent_run(
    input_data: schemas.AgentRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> schemas.AgentRun:
    await get_conversation_or_404(db, input_data.session_id, current_user, require_write=True)
    run = await create_db_agent_run(
        db,
        input_data.session_id,
        title=input_data.skill_key or "Agent Run",
        status="queued",
        progress=0,
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> schemas.AgentRun:
    run = await get_db_agent_run(db, run_id, current_user)
    events = await list_run_events(db, run_id)
    return to_agent_run_schema(run, events)


@router.post("/{run_id}/cancel", response_model=schemas.AgentRun)
async def cancel_agent_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> schemas.AgentRun:
    run = await get_db_agent_run(db, run_id, current_user)
    await get_conversation_or_404(db, run.conversation_id, current_user, require_write=True)
    adapter = _get_adapter(None)
    if adapter is not None:
        await adapter.cancel_run(run_id)
    event = await finish_db_agent_run(
        db,
        run,
        status="cancelled",
        label="Agent run cancelled",
    )
    events = await list_run_events(db, run_id)
    if event not in events:
        events.append(event)
    return to_agent_run_schema(run, events)


@router.get("/{run_id}/events")
async def stream_agent_run_events(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    run = await get_db_agent_run(db, run_id, current_user)

    async def event_stream():
        events = await list_run_events(db, run_id)
        for event in events:
            api_event = to_agent_run_event_schema(event, run)
            yield (
                "event: agent_run_event\n"
                f"data: {json.dumps(api_event.model_dump(by_alias=True), ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
