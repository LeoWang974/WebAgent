import asyncio
import logging
from datetime import datetime

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models import AgentRun, AgentRunEvent, Conversation, Message, User
from app.services.adapter_limiter import (
    AdapterCapacityTimeout,
    acquire_adapter_capacity,
)
from app.services.agent_run_artifact_service import (
    discover_and_persist_run_artifacts,
    final_assistant_message,
)
from app.services.agent_run_control import (
    AgentRunCancelled,
    AgentRunTimeout,
    is_agent_run_cancelled,
)
from app.services.agent_run_workspace import (
    run_artifacts_dir,
    run_workspace_dir,
    stage_conversation_artifacts,
)
from app.services.agent_runs import (
    create_hermes_adapter,
    finish_db_agent_run,
    record_db_agent_run_event,
)
from app.services.model_runtime_config import model_runtime_config_builder
from app.services.persistence import persist_message, to_artifact, to_message, to_session
from app.services.runtime_environment import (
    build_user_runtime_context,
    scrub_runtime_credentials,
)
from app.services.session_artifacts import artifact_display_priority, refresh_conversation
from app.services.stage_bubble_filter import should_suppress_stage_bubble
from app.services.stream_protocol import runtime_diagnostics

logger = logging.getLogger(__name__)


async def _load_run_context(
    db: AsyncSession,
    run_id: str,
) -> tuple[AgentRun, Conversation, User, dict]:
    run = await db.get(AgentRun, run_id)
    if run is None:
        raise RuntimeError(f"Agent run not found: {run_id}")

    conversation = await db.get(Conversation, run.conversation_id)
    if conversation is None:
        raise RuntimeError(f"Conversation not found for run: {run_id}")

    user = await db.get(User, conversation.user_id)
    if user is None:
        raise RuntimeError(f"User not found for conversation: {conversation.id}")

    result = await db.execute(
        select(AgentRunEvent).where(
            AgentRunEvent.run_id == run_id,
            AgentRunEvent.event_type == "queued",
        )
    )
    queued_event = result.scalars().first()
    payload = queued_event.payload if queued_event is not None else {}
    return run, conversation, user, payload or {}


async def _message_snapshot(db: AsyncSession, message: Message) -> tuple[str, dict]:
    message_id = message.__dict__.get("id")
    if message_id is None:
        identity = sa_inspect(message).identity
        message_id = identity[0] if identity else None
    if message_id is None:
        raise RuntimeError("Assistant message identity is unavailable.")

    required_fields = {"id", "conversation_id", "role", "content", "created_at", "artifact_ids"}
    if not required_fields.issubset(message.__dict__):
        loaded_message = await db.get(Message, message_id)
        if loaded_message is None:
            raise RuntimeError(f"Assistant message not found: {message_id}")
        message = loaded_message

    content = str(message.__dict__.get("content") or "")
    return content, to_message(message).model_dump(by_alias=True)


async def execute_queued_agent_run(run_id: str) -> None:
    async with AsyncSessionLocal() as db:
        await _execute_queued_agent_run(db, run_id)


async def _execute_queued_agent_run(db: AsyncSession, run_id: str) -> None:
    run, conversation, user, queued_payload = await _load_run_context(db, run_id)
    run_id_value = run.id
    conversation_id = conversation.id
    user_id = user.id
    current_adapter_key = "hermes"
    logger.info(
        "Queued agent run loaded: run_id=%s conversation_id=%s adapter=%s status=%s",
        run_id_value,
        conversation_id,
        current_adapter_key,
        run.status,
    )
    if run.status != "queued":
        logger.info(
            "Skipping non-queued agent run task: run_id=%s status=%s",
            run_id_value,
            run.status,
        )
        return
    content = str(queued_payload.get("content") or "")
    model_id = queued_payload.get("modelId")
    run_started_at = run.created_at or datetime.now()
    assistant_messages: list[Message] = []
    assistant_output_parts: list[str] = []
    assistant_event_count = 0
    stage_bubble_counts: dict[str, int] = {}
    last_stage_bubble_key: str | None = None
    artifact_discovery_summary: dict[str, object] = {}
    adapter = None
    adapter_capacity_lease = None
    user_runtime_context = None
    run_started_monotonic = asyncio.get_running_loop().time()
    model_runtime_config = None

    try:
        model_runtime_config = model_runtime_config_builder.build_for_run(run)
        user_runtime_context = build_user_runtime_context(
            user,
            conversation_id,
            run_id=run_id_value,
            model_runtime_config=model_runtime_config,
        )
        run_workspace = run_workspace_dir(run_id_value, conversation_id, user_id)
        staged_context_artifacts = await stage_conversation_artifacts(
            db,
            conversation_id,
            run_workspace,
            mirror_dirs=(user_runtime_context.hermes_home / "context",),
        )
        logger.info(
            "Staged conversation artifacts: run_id=%s count=%s workspace=%s",
            run_id_value,
            len(staged_context_artifacts),
            run_workspace,
        )
        logger.info(
            "Resolving adapter for queued run: run_id=%s adapter=%s",
            run_id_value,
            current_adapter_key,
        )
        adapter = create_hermes_adapter(
            user,
            conversation_id=conversation_id,
            run_id=run_id_value,
            model_runtime_config=model_runtime_config,
        )
        if await is_agent_run_cancelled(db, run_id_value):
            raise AgentRunCancelled()
        run.adapter_key = current_adapter_key
        logger.info(
            "Resolved adapter for queued run: run_id=%s adapter=%s available=%s",
            run_id_value,
            current_adapter_key,
            adapter is not None,
        )
        await record_db_agent_run_event(
            db,
            run,
            event_type="started",
            label="Agent run started",
            status="running",
            progress=5,
            step_status="running",
            payload={
                "content": content,
                "modelId": model_id,
                "adapterKey": current_adapter_key,
                "adapterLockScope": user_runtime_context.adapter_lock_scope(),
                "userRuntimeRoot": str(user_runtime_context.root_dir),
                "workspaceDir": str(run_workspace),
                "contextArtifacts": [str(path) for path in staged_context_artifacts],
            },
        )
        if adapter is None:
            raise RuntimeError("No agent runtime adapter is available.")

        async def on_adapter_capacity_wait(elapsed_seconds: float) -> None:
            if await is_agent_run_cancelled(db, run_id_value):
                raise AgentRunCancelled()
            await record_db_agent_run_event(
                db,
                run,
                event_type="adapter_capacity_wait",
                label=(
                    f"Waiting for {current_adapter_key or 'agent'} adapter capacity "
                    f"({int(elapsed_seconds)}s)."
                ),
                status="running",
                progress=5,
                step_status="running",
                payload={
                    "adapterKey": current_adapter_key,
                    "elapsedSeconds": int(elapsed_seconds),
                },
            )

        adapter_capacity_lease = await acquire_adapter_capacity(
            current_adapter_key,
            run_id_value,
            scope=user_runtime_context.adapter_lock_scope(),
            on_wait=on_adapter_capacity_wait,
        )
        logger.info("Acquired adapter capacity lease object: run_id=%s", run_id_value)
        await adapter_capacity_lease.__aenter__()
        logger.info("Entered adapter capacity lease: run_id=%s", run_id_value)
        await record_db_agent_run_event(
            db,
            run,
            event_type="adapter_capacity_acquired",
            label=f"Acquired {current_adapter_key or 'agent'} adapter capacity.",
            status="running",
            progress=5,
            payload={
                "adapterKey": current_adapter_key,
                "adapterLockScope": user_runtime_context.adapter_lock_scope(),
            },
        )
        if await is_agent_run_cancelled(db, run_id_value):
            raise AgentRunCancelled()

        from agent_runtime.schemas import AgentRunCreate as AdapterAgentRunCreate

        adapter_input = AdapterAgentRunCreate(
            content=content,
            session_id=conversation_id,
            model_id=model_id,
            run_id=run_id_value,
            working_dir=str(run_workspace),
            artifacts_dir=str(run_artifacts_dir(run_id_value, conversation_id, user_id)),
        )

        stream = adapter.stream_response_events(adapter_input)
        logger.info(
            "Starting adapter stream loop: run_id=%s adapter=%s",
            run_id_value,
            current_adapter_key,
        )
        while True:
            elapsed_seconds = asyncio.get_running_loop().time() - run_started_monotonic
            overall_remaining = settings.agent_run_overall_timeout_seconds - elapsed_seconds
            if overall_remaining <= 0:
                if hasattr(adapter, "cancel_run"):
                    await adapter.cancel_run(run_id_value)
                raise AgentRunTimeout(
                    "overall_timeout",
                    "Agent run exceeded the overall task timeout.",
                )

            wait_timeout = min(
                settings.agent_run_idle_timeout_seconds,
                max(1, overall_remaining),
            )
            timeout_type = (
                "overall_timeout"
                if wait_timeout < settings.agent_run_idle_timeout_seconds
                else "idle_timeout"
            )
            try:
                logger.info("Waiting for adapter stream chunk: run_id=%s", run_id_value)
                chunk = await asyncio.wait_for(stream.__anext__(), timeout=wait_timeout)
                logger.info("Received adapter stream chunk: run_id=%s", run_id_value)
            except StopAsyncIteration:
                break
            except TimeoutError as error:
                if hasattr(adapter, "cancel_run"):
                    await adapter.cancel_run(run_id_value)
                if timeout_type == "overall_timeout":
                    raise AgentRunTimeout(
                        "overall_timeout",
                        "Agent run exceeded the overall task timeout.",
                    ) from error
                raise AgentRunTimeout(
                    "idle_timeout",
                    (
                        "Agent runtime did not emit output within "
                        f"{settings.agent_run_idle_timeout_seconds} seconds."
                    ),
                ) from error

            if await is_agent_run_cancelled(db, run_id_value):
                raise AgentRunCancelled()

            if hasattr(chunk, "step"):
                step = getattr(chunk, "step", None)
                message_content = str(getattr(step, "label", "") or "").strip()
                event_type = str(getattr(chunk, "event_type", "stage_update"))
                event_payload = dict(getattr(chunk, "payload", {}) or {})
                progress = int(getattr(chunk, "progress", 0) or 0)
            else:
                message_content = str(chunk).strip()
                event_type = "stage_update"
                event_payload = {}
                progress = 0
            if not message_content:
                continue

            progress = progress or min(90, 10 + assistant_event_count * 8)
            should_suppress, stage_key = should_suppress_stage_bubble(
                message_content,
                event_payload,
                stage_bubble_counts,
                last_stage_bubble_key,
            )
            last_stage_bubble_key = stage_key
            if should_suppress:
                await record_db_agent_run_event(
                    db,
                    run,
                    event_type="raw_activity",
                    label=message_content,
                    status="running",
                    progress=progress,
                    payload={
                        **event_payload,
                        "stageKey": stage_key,
                        "suppressedStageBubble": True,
                    },
                )
                continue

            if event_type == "artifact_found":
                await record_db_agent_run_event(
                    db,
                    run,
                    event_type=event_type,
                    label=message_content,
                    status="running",
                    progress=progress,
                    payload=event_payload,
                )
                continue

            assistant_message = await persist_message(
                db,
                conversation_id,
                "assistant",
                message_content,
            )
            assistant_output_parts.append(message_content)
            assistant_messages.append(assistant_message)
            assistant_event_count += 1
            await record_db_agent_run_event(
                db,
                run,
                event_type=event_type,
                label=message_content,
                status="running",
                progress=progress,
                payload={
                    "content": message_content,
                    "messageId": assistant_message.id,
                    "stageKey": stage_key,
                    **event_payload,
                },
            )

        if await is_agent_run_cancelled(db, run_id_value):
            diagnostics = (
                adapter.get_last_diagnostics()
                if hasattr(adapter, "get_last_diagnostics")
                else {}
            )
            adapter_completed = bool(diagnostics.get("completion_detected")) or (
                diagnostics.get("exit_code") == 0
            )
            if not adapter_completed:
                raise AgentRunCancelled()

        fresh_run = await db.get(AgentRun, run_id_value)
        if fresh_run is None:
            return
        run = fresh_run
        response_artifacts = await discover_and_persist_run_artifacts(
            db,
            run,
            conversation_id,
            run_started_at,
            adapter,
            artifact_discovery_summary,
            user_id,
            content,
            "\n\n".join(assistant_output_parts),
        )
        assistant_message = await final_assistant_message(
            db,
            conversation_id,
            assistant_messages,
            response_artifacts,
        )
        assistant_message_content, assistant_message_payload = await _message_snapshot(
            db,
            assistant_message,
        )
        for artifact in sorted(response_artifacts, key=artifact_display_priority):
            await record_db_agent_run_event(
                db,
                run,
                event_type="artifact_created",
                label=f"Artifact created: {artifact.title}",
                status="rendering",
                progress=95,
                payload={
                    "artifact": to_artifact(artifact).model_dump(by_alias=True),
                    "artifactId": artifact.id,
                    "artifactType": artifact.type,
                    "messageId": assistant_message.id,
                    "sessionId": conversation_id,
                    "title": artifact.title,
                },
            )

        await _complete_run(
            db,
            run,
            conversation_id,
            assistant_message_content,
            assistant_message_payload,
        )
    except AgentRunCancelled:
        await db.rollback()
        run = await db.get(AgentRun, run_id_value)
        if run is None:
            return
        await finish_db_agent_run(db, run, status="cancelled", label="Agent run cancelled")
        conversation = await refresh_conversation(db, conversation_id)
        conversation.status = "active"
        await db.commit()
    except AgentRunTimeout as error:
        logger.warning("Queued agent run timed out: %s", error)
        await db.rollback()
        run = await db.get(AgentRun, run_id_value)
        if run is None:
            return
        await record_db_agent_run_event(
            db,
            run,
            event_type="diagnostic",
            label="Agent runtime timeout diagnostics",
            status="failed",
            progress=run.progress,
            step_status="failed",
            payload=runtime_diagnostics(adapter, artifact_discovery_summary),
        )
        await finish_db_agent_run(
            db,
            run,
            status="failed",
            label=f"Agent run timeout: {error.timeout_type}",
            error=str(error),
        )
        await _fail_conversation(db, run, conversation_id, f"Agent runtime timeout: {error}")
    except AdapterCapacityTimeout as error:
        logger.warning("Queued agent run could not acquire adapter capacity: %s", error)
        await db.rollback()
        run = await db.get(AgentRun, run_id_value)
        if run is None:
            return
        await finish_db_agent_run(
            db,
            run,
            status="failed",
            label="Agent adapter capacity wait timed out",
            error=str(error),
        )
        await _fail_conversation(db, run, conversation_id, f"Agent runtime error: {error}")
    except Exception as error:
        logger.exception("Queued agent run failed")
        if adapter is not None and hasattr(adapter, "cancel_run"):
            await adapter.cancel_run(run_id_value)
        await db.rollback()
        run = await db.get(AgentRun, run_id_value)
        if run is None:
            return
        if await is_agent_run_cancelled(db, run_id_value):
            await finish_db_agent_run(
                db,
                run,
                status="cancelled",
                label="Agent run cancelled",
            )
            conversation = await refresh_conversation(db, conversation_id)
            conversation.status = "active"
            await db.commit()
            return
        await record_db_agent_run_event(
            db,
            run,
            event_type="diagnostic",
            label="Agent runtime failure diagnostics",
            status="failed",
            progress=run.progress,
            step_status="failed",
            payload=runtime_diagnostics(adapter, artifact_discovery_summary),
        )
        await finish_db_agent_run(
            db,
            run,
            status="failed",
            label="Agent run failed",
            error=str(error),
        )
        await _fail_conversation(db, run, conversation_id, f"Agent runtime error: {error}")
    finally:
        if adapter_capacity_lease is not None:
            await adapter_capacity_lease.__aexit__(None, None, None)
        if user_runtime_context is not None:
            scrub_runtime_credentials(user_runtime_context)


async def _complete_run(
    db: AsyncSession,
    run: AgentRun,
    conversation_id: str,
    assistant_message_content: str,
    assistant_message_payload: dict,
) -> None:
    run_id_value = run.id
    conversation = await refresh_conversation(db, conversation_id)
    conversation.status = "active"
    await finish_db_agent_run(
        db,
        run,
        status="completed",
        label="Agent run completed",
        output=assistant_message_content,
    )
    await db.commit()
    conversation = await refresh_conversation(db, conversation_id)
    await record_db_agent_run_event(
        db,
        run,
        event_type="assistant_done",
        label="Assistant response completed",
        status="completed",
        progress=100,
        payload={
            "message": assistant_message_payload,
            "session": to_session(conversation).model_dump(by_alias=True),
            "runId": run_id_value,
            "status": "completed",
        },
    )


async def _fail_conversation(
    db: AsyncSession,
    run: AgentRun,
    conversation_id: str,
    message: str,
) -> None:
    error_message = await persist_message(db, conversation_id, "assistant", message)
    conversation = await refresh_conversation(db, conversation_id)
    conversation.status = "failed"
    await db.commit()
    await record_db_agent_run_event(
        db,
        run,
        event_type="assistant_done",
        label="Assistant response failed",
        status="failed",
        progress=100,
        payload={"messageId": error_message.id, "status": "failed"},
    )
