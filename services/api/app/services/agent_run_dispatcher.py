from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.core.config import settings
from app.services.agent_runs import (
    create_db_agent_run,
    record_db_agent_run_event,
    resolve_adapter_for_model,
)
from app.services.model_runtime_config import model_runtime_config_builder
from app.services.persistence import persist_message


async def enqueue_agent_run_message(
    db: AsyncSession,
    session_id: str,
    input_data: schemas.MessageCreate,
    current_user,
    resolved_skill_key: str | None,
):
    user_message = await persist_message(db, session_id, "user", input_data.content)
    model_runtime_config = await model_runtime_config_builder.build_for_user(
        db,
        current_user,
        input_data.model_id,
    )
    adapter_key, _ = await resolve_adapter_for_model(
        db,
        current_user,
        input_data.model_id,
        adapter_key=input_data.adapter_key,
        conversation_id=session_id,
        model_runtime_config=model_runtime_config,
    )
    run = await create_db_agent_run(
        db,
        session_id,
        title=resolved_skill_key or "Agent Run",
        status="queued",
        progress=0,
        adapter_key=adapter_key,
        model_runtime_config=model_runtime_config,
    )
    await record_db_agent_run_event(
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
            "adapterKey": adapter_key,
            "requestedAdapterKey": input_data.adapter_key,
            "modelConfigId": run.model_config_id,
            "modelProvider": run.model_provider,
            "modelName": run.model_name,
            "skillKey": resolved_skill_key,
            "userMessageId": user_message.id,
        },
    )
    from app.workers.agent_run_tasks import execute_agent_run_task

    execute_agent_run_task.apply_async((run.id,), queue=settings.agent_run_queue_name)
    return user_message, run
