import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import schemas
from app.schemas.agent_run import AgentRunStep
from app.core.config import settings
from app.services import mock_store

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


def _to_api_step(step) -> schemas.AgentRunStep:
    return schemas.AgentRunStep(
        id=getattr(step, "id", mock_store.new_id("step")),
        label=getattr(step, "label", "Step"),
        status=getattr(step, "status", "running"),
        timestamp=getattr(step, "timestamp", None) or mock_store.now_iso(),
    )


def _to_api_event(event) -> schemas.AgentRunEvent:
    api_step = _to_api_step(event.step)
    completed_at = getattr(event, "completed_at", None)

    if getattr(event, "status", None) == "completed" and not completed_at:
        completed_at = mock_store.now_iso()

    return schemas.AgentRunEvent(
        run_id=getattr(event, "run_id", ""),
        status=getattr(event, "status", "running"),
        progress=getattr(event, "progress", 0),
        completed_at=completed_at,
        step=api_step,
    )


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


def _get_adapter_for_run(run: schemas.AgentRun):
    run_marker = f"{run.id} {run.title}".lower()

    if "openclaw" in run_marker:
        return _get_adapter("model_openclaw")
    if "hermes" in run_marker:
        return _get_adapter("model_hermes")

    return _get_adapter(None)


@router.post("", response_model=schemas.AgentRun)
async def create_agent_run(input_data: schemas.AgentRunCreate) -> schemas.AgentRun:
    adapter = _get_adapter(input_data.model_id)

    if adapter:
        try:
            from agent_runtime.schemas import AgentRunCreate as AdapterAgentRunCreate

            adapter_input = AdapterAgentRunCreate(
                content=input_data.content,
                session_id=input_data.session_id,
                skill_key=input_data.skill_key,
                model_id=input_data.model_id,
            )
            run = await adapter.create_run(adapter_input)
            adapter_run = schemas.AgentRun(
                id=run.id,
                session_id=run.session_id,
                status=run.status,
                title=run.title,
                progress=run.progress,
                steps=[
                    AgentRunStep(
                        id=step.id,
                        label=step.label,
                        status=step.status,
                        timestamp=step.timestamp or mock_store.now_iso(),
                    )
                    for step in run.steps
                ],
                started_at=run.started_at or mock_store.now_iso(),
                completed_at=run.completed_at,
                error=run.error,
            )
            mock_store.runs.insert(0, adapter_run)
            return adapter_run
        except Exception as e:
            error_run = schemas.AgentRun(
                id=f"run_error_{input_data.session_id}",
                session_id=input_data.session_id,
                status="failed",
                title="Hermes Agent Run",
                progress=0,
                steps=[],
                started_at=mock_store.now_iso(),
                error=str(e),
            )
            mock_store.runs.insert(0, error_run)
            return error_run

    run = schemas.AgentRun(
        id=mock_store.new_id("run"),
        session_id=input_data.session_id,
        status="queued",
        title="Agent Run",
        progress=0,
        steps=[],
        started_at=mock_store.now_iso(),
    )
    mock_store.runs.insert(0, run)
    return run


@router.get("/{run_id}", response_model=schemas.AgentRun)
async def get_agent_run(run_id: str) -> schemas.AgentRun:
    run = next((item for item in mock_store.runs if item.id == run_id), None)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@router.post("/{run_id}/cancel", response_model=schemas.AgentRun)
async def cancel_agent_run(run_id: str) -> schemas.AgentRun:
    run = next((item for item in mock_store.runs if item.id == run_id), None)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    updated = run.model_copy(
        update={"status": "cancelled", "completed_at": mock_store.now_iso()}
    )
    mock_store.runs[:] = [updated if item.id == run_id else item for item in mock_store.runs]
    return updated


@router.get("/{run_id}/events")
async def stream_agent_run_events(run_id: str) -> StreamingResponse:
    run = next((item for item in mock_store.runs if item.id == run_id), None)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")

    adapter = _get_adapter_for_run(run)

    async def event_stream():
        if adapter:
            async for event in adapter.stream_events(run_id):
                api_event = _to_api_event(event)
                yield f"event: agent_run_event\ndata: {api_event.model_dump_json(by_alias=True)}\n\n"
        else:
            steps = [
                ("Queued request", 12, "queued"),
                ("Selected skill and model", 32, "running"),
                ("Calling agent tools", 58, "tool_calling"),
                ("Preparing artifact preview", 82, "rendering"),
                ("Completed response", 100, "completed"),
            ]
            for index, (label, progress, status) in enumerate(steps):
                await asyncio.sleep(0.45)
                timestamp = mock_store.now_iso()
                event = schemas.AgentRunEvent(
                    run_id=run_id,
                    status=status,
                    progress=progress,
                    completed_at=timestamp if status == "completed" else None,
                    step=schemas.AgentRunStep(
                        id=f"{run_id}_step_{index}",
                        label=label,
                        status="completed" if status == "completed" else "running",
                        timestamp=timestamp,
                    ),
                )
                yield f"event: agent_run_event\ndata: {event.model_dump_json(by_alias=True)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
