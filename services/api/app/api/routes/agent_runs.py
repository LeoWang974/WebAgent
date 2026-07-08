import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import schemas
from app.services import mock_store

router = APIRouter()


@router.post("", response_model=schemas.AgentRun)
async def create_agent_run(input_data: schemas.AgentRunCreate) -> schemas.AgentRun:
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
    steps = [
        ("Queued request", 12, "queued"),
        ("Selected skill and model", 32, "running"),
        ("Calling agent tools", 58, "tool_calling"),
        ("Preparing artifact preview", 82, "rendering"),
        ("Completed response", 100, "completed"),
    ]

    async def event_stream():
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

