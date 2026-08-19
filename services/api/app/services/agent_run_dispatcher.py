from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.core.config import settings
from app.models import Conversation
from app.services.agent_run_queue import estimated_queue_position, queue_for_message
from app.services.agent_runs import create_db_agent_run, record_db_agent_run_event
from app.services.model_runtime_config import model_runtime_config_builder
from app.services.persistence import persist_message


async def enqueue_agent_run_message(
    db: AsyncSession,
    session_id: str,
    input_data: schemas.MessageCreate,
    current_user,
):
    """Persist a user message and queue an isolated Hermes run."""
    user_message = await persist_message(
        db,
        session_id,
        "user",
        input_data.content,
        commit=False,
    )
    model_runtime_config = await model_runtime_config_builder.build_for_user(
        db,
        current_user,
        input_data.model_id,
    )
    run = await create_db_agent_run(
        db,
        session_id,
        title="Hermes Agent Run",
        status="queued",
        progress=0,
        adapter_key="hermes",
        model_runtime_config=model_runtime_config,
        commit=False,
    )
    queue_name, queue_reason = queue_for_message(input_data.content)
    queue_position = await estimated_queue_position(queue_name)
    conversation = await db.get(Conversation, session_id)
    if conversation is not None:
        conversation.status = "running"
    await record_db_agent_run_event(
        db,
        run,
        event_type="queued",
        label=f"{queue_reason}，当前位置约 {queue_position}" if queue_position else queue_reason,
        status="queued",
        progress=0,
        step_status="pending",
        payload={
            "content": input_data.content,
            "modelId": input_data.model_id,
            "adapterKey": "hermes",
            "modelConfigId": run.model_config_id,
            "modelProvider": run.model_provider,
            "modelName": run.model_name,
            "queueName": queue_name,
            "queuePosition": queue_position,
            "queueReason": queue_reason,
            "userMessageId": user_message.id,
        },
    )
    if settings.agent_run_queue_enabled:
        from app.workers.agent_run_tasks import execute_agent_run_task

        execute_agent_run_task.apply_async((run.id,), queue=queue_name)
    else:
        from app.services.agent_run_executor import _execute_queued_agent_run

        await _execute_queued_agent_run(db, run.id)
        await db.refresh(user_message)
        await db.refresh(run)
    return user_message, run
