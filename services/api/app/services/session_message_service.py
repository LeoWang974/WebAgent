from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.models import Conversation, User
from app.services.agent_runs import (
    create_db_agent_run,
    finish_db_agent_run,
    record_db_agent_run_event,
    resolve_adapter_for_model,
)
from app.services.model_runtime_config import model_runtime_config_builder
from app.services.persistence import persist_message, to_message, to_session
from app.services.session_artifacts import refresh_conversation


def resolve_skill_key(content: str, explicit_skill_key: str | None) -> str | None:
    void_content = content
    del void_content
    return explicit_skill_key


async def send_message_core(
    db: AsyncSession,
    conversation: Conversation,
    input_data: schemas.MessageCreate,
    current_user: User,
) -> schemas.SendMessageResult:
    session_id = conversation.id
    resolved_skill_key = resolve_skill_key(input_data.content, input_data.skill_key)
    user_message = await persist_message(db, session_id, "user", input_data.content)

    assistant_content = "Agent runtime did not return a response."
    run = None

    try:
        model_runtime_config = await model_runtime_config_builder.build_for_user(
            db,
            current_user,
            input_data.model_id,
        )
        adapter_key, adapter = await resolve_adapter_for_model(
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
            status="running",
            progress=5,
            adapter_key=adapter_key,
            model_runtime_config=model_runtime_config,
        )
        await record_db_agent_run_event(
            db,
            run,
            event_type="started",
            label="Agent run started",
            status="running",
            progress=5,
            payload={
                "content": input_data.content,
                "modelId": input_data.model_id,
                "requestedAdapterKey": input_data.adapter_key,
                "modelConfigId": run.model_config_id,
                "modelProvider": run.model_provider,
                "modelName": run.model_name,
                "skillKey": resolved_skill_key,
                "adapterKey": adapter_key,
            },
        )

        if adapter is None:
            assistant_content = "No agent runtime adapter is available."
            await finish_db_agent_run(
                db,
                run,
                status="failed",
                label="Agent runtime adapter unavailable",
                error=assistant_content,
            )
            run = None

        if run is not None:
            from agent_runtime.schemas import AgentRunCreate as AdapterAgentRunCreate

            runtime_run = await adapter.create_run(
                AdapterAgentRunCreate(
                    content=input_data.content,
                    session_id=session_id,
                    skill_key=resolved_skill_key,
                    model_id=input_data.model_id,
                )
            )
            assistant_content = (
                getattr(runtime_run, "output", None) or runtime_run.error or assistant_content
            )
            await finish_db_agent_run(
                db,
                run,
                status="completed",
                label="Agent run completed",
                output=assistant_content,
            )
    except Exception as error:
        assistant_content = f"Agent runtime error: {error}"
        if run is not None:
            await finish_db_agent_run(
                db,
                run,
                status="failed",
                label="Agent run failed",
                error=str(error),
            )

    assistant_message = await persist_message(db, session_id, "assistant", assistant_content)
    conversation.status = "active"
    await db.commit()
    conversation = await refresh_conversation(db, conversation.id)
    return schemas.SendMessageResult(
        messages=[to_message(user_message), to_message(assistant_message)],
        session=to_session(conversation),
    )
