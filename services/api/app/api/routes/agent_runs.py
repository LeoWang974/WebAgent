import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
from app.core.config import settings
from app.integrations.hermes.process_registry import terminate_registered_run_process
from app.services.agent_run_dispatcher import enqueue_agent_run_message
from app.services.agent_runs import (
    TERMINAL_RUN_STATUSES,
    AgentRunEventCursor,
    create_hermes_adapter,
    finish_db_agent_run,
    get_db_agent_run,
    list_agent_runs_for_user,
    list_new_run_events,
    list_run_events,
    to_agent_run_event_schema,
    to_agent_run_schema,
)
from app.services.model_runtime_config import model_runtime_config_builder
from app.services.persistence import get_conversation_or_404
from app.services.stream_protocol import SSE_HEADERS, sse

router = APIRouter()


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
    _, run = await enqueue_agent_run_message(
        db,
        input_data.session_id,
        schemas.MessageCreate(content=input_data.content, model_id=input_data.model_id),
        current_user,
    )
    return to_agent_run_schema(run, await list_run_events(db, run.id))


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
    if run.status in TERMINAL_RUN_STATUSES:
        events = await list_run_events(db, run_id)
        return to_agent_run_schema(run, events)
    adapter_cancelled = False
    adapter_error = None
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
        event_cursor = AgentRunEventCursor()
        try:
            while True:
                run = await get_db_agent_run(db, run_id, current_user)
                events = await list_new_run_events(db, run_id, event_cursor)
                encoded_events: list[str] = []
                for event in events:
                    api_event = to_agent_run_event_schema(event, run)
                    encoded_events.append(
                        sse("agent_run_event", api_event.model_dump(by_alias=True))
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
