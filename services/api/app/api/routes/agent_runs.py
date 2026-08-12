import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
from app.core.config import settings
from app.services.agent_runs import (
    TERMINAL_RUN_STATUSES,
    create_db_agent_run,
    finish_db_agent_run,
    get_db_agent_run,
    list_agent_runs_for_user,
    list_run_events,
    record_db_agent_run_event,
    create_hermes_adapter,
    to_agent_run_event_schema,
    to_agent_run_schema,
)
from app.services.model_runtime_config import model_runtime_config_builder
from app.services.persistence import get_conversation_or_404

try:
    from agent_runtime.adapters.process_registry import terminate_registered_run_process
except ImportError:
    terminate_registered_run_process = None

router = APIRouter()
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get("", response_model=list[schemas.AgentRun])
async def list_agent_runs(
    db: DbSession,
    current_user: CurrentUser,
    session_id: str | None = None,
) -> list[schemas.AgentRun]:
    return await list_agent_runs_for_user(db, current_user, session_id)


@router.post("", response_model=schemas.AgentRun)
async def create_agent_run(
    input_data: schemas.AgentRunCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.AgentRun:
    await get_conversation_or_404(db, input_data.session_id, current_user, require_write=True)
    model_runtime_config = await model_runtime_config_builder.build_for_user(
        db,
        current_user,
        input_data.model_id,
    )
    run = await create_db_agent_run(
        db,
        input_data.session_id,
        title="Hermes Agent Run",
        status="queued",
        progress=0,
        adapter_key="hermes",
        model_runtime_config=model_runtime_config,
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
            "modelConfigId": run.model_config_id,
            "modelProvider": run.model_provider,
            "modelName": run.model_name,
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
    adapter_cancelled = False
    adapter_error = None
    if terminate_registered_run_process is not None:
        try:
            adapter_cancelled = await terminate_registered_run_process(run_id)
        except Exception as error:
            adapter_error = str(error)
    model_runtime_config = model_runtime_config_builder.build_for_run(run)
    adapter = None
    try:
        adapter = create_hermes_adapter(
            current_user,
            conversation_id=run.conversation_id,
            run_id=run.id,
            model_runtime_config=model_runtime_config,
        )
    except Exception as error:
        adapter_error = str(error) if adapter_error is None else adapter_error
    if adapter is not None:
        try:
            await adapter.cancel_run(run_id)
            adapter_cancelled = True
        except Exception as error:
            adapter_error = str(error)
    if terminate_registered_run_process is not None:
        try:
            await asyncio.sleep(1)
            adapter_cancelled = await terminate_registered_run_process(run_id) or adapter_cancelled
        except Exception as error:
            adapter_error = str(error) if adapter_error is None else adapter_error
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
    await db.close()

    async def event_stream():
        sent_event_ids: set[str] = set()
        try:
            while True:
                run = await get_db_agent_run(db, run_id, current_user)
                events = await list_run_events(db, run_id)
                encoded_events: list[str] = []
                for event in events:
                    if event.id in sent_event_ids:
                        continue
                    sent_event_ids.add(event.id)
                    api_event = to_agent_run_event_schema(event, run)
                    event_data = json.dumps(
                        api_event.model_dump(by_alias=True),
                        ensure_ascii=False,
                    )
                    encoded_events.append(
                        f"event: agent_run_event\ndata: {event_data}\n\n"
                    )
                is_terminal = run.status in TERMINAL_RUN_STATUSES
                # Do not retain a database connection while waiting on the client or poll timer.
                await db.close()
                for encoded_event in encoded_events:
                    yield encoded_event
                if is_terminal:
                    break
                yield ": heartbeat\n\n"
                await asyncio.sleep(settings.agent_run_event_poll_interval_seconds)
        finally:
            await db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
