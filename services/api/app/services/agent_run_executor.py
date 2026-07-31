import asyncio
import logging
import subprocess
from datetime import datetime

import httpx
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.settings import DEFAULT_INTERFACE, to_interface_schema
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models import AgentRun, AgentRunEvent, Conversation, Message, User, UserSettings
from app.services.adapter_limiter import (
    AdapterCapacityTimeout,
    acquire_adapter_capacity,
)
from app.services.agent_run_workspace import run_workspace_dir
from app.services.agent_runs import (
    finish_db_agent_run,
    record_db_agent_run_event,
    resolve_adapter_for_model,
)
from app.services.agent_runtime_context import build_user_runtime_context
from app.services.artifact_discovery import (
    create_markdown_artifact_from_content,
    create_pptx_from_html_artifacts,
    discover_artifacts_with_retry,
    discover_related_artifact_paths,
    extract_artifact_path_strings,
)
from app.services.model_runtime_config import model_runtime_config_builder
from app.services.persistence import persist_message, to_artifact, to_message, to_session
from app.services.session_artifacts import (
    artifact_display_priority,
    is_debug_artifact,
    persist_discovered_artifacts,
    refresh_conversation,
)
from app.services.session_stream_service import (
    AgentRunCancelled,
    AgentRunTimeout,
    is_agent_run_cancelled,
    runtime_diagnostics,
    should_suppress_stage_bubble,
)

logger = logging.getLogger(__name__)
PRIMARY_ARTIFACT_TYPES_BY_SKILL = {
    "data_analysis": {"data_table", "markdown_report", "html_page"},
    "deep_research": {"markdown_report", "html_page"},
    "html_generation": {"html_page"},
    "ppt_generation": {"ppt_deck"},
    "u1_image": {"image_result"},
}


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


async def _user_developer_mode_by_id(db: AsyncSession, user_id: str) -> bool:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    user_settings = result.scalar_one_or_none()
    if user_settings is None:
        user_settings = UserSettings(
            user_id=user_id,
            data_context={},
            interface=DEFAULT_INTERFACE,
        )
        db.add(user_settings)
        await db.commit()
    return to_interface_schema(user_settings).developer_mode


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


async def _complete_plain_chat_with_sensenova(
    db: AsyncSession,
    run: AgentRun,
    conversation: Conversation,
    content: str,
) -> None:
    model_runtime_config = model_runtime_config_builder.build_for_run(run)
    if not model_runtime_config.supports_openai_chat_completions():
        return

    run.adapter_key = run.adapter_key or "sensenova"
    await record_db_agent_run_event(
        db,
        run,
        event_type="started",
        label="Plain chat started",
        status="running",
        progress=10,
        step_status="running",
        payload={"adapterKey": "sensenova", "mode": "direct_chat"},
    )
    base_url = (model_runtime_config.base_url or "https://token.sensenova.cn/v1").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {model_runtime_config.api_key}"},
                json={
                    "model": model_runtime_config.model_name,
                    "messages": [{"role": "user", "content": content}],
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as error:
        detail = error.response.text[:500]
        message = f"SenseNova chat error: {error.response.status_code} {detail}"
        raise RuntimeError(message) from error
    except httpx.HTTPError as error:
        raise RuntimeError(f"SenseNova chat request failed: {error}") from error

    payload = response.json()
    reply = payload.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    if not reply:
        raise RuntimeError("SenseNova chat returned an empty response.")

    assistant_message = await persist_message(db, conversation.id, "assistant", reply)
    await record_db_agent_run_event(
        db,
        run,
        event_type="stage_update",
        label=reply,
        status="running",
        progress=90,
        payload={
            "content": reply,
            "directPlainChat": True,
            "messageId": assistant_message.id,
        },
    )
    await _complete_run(
        db,
        run,
        conversation.id,
        *(await _message_snapshot(db, assistant_message)),
    )


async def _execute_queued_agent_run(db: AsyncSession, run_id: str) -> None:
    run, conversation, user, queued_payload = await _load_run_context(db, run_id)
    run_id_value = run.id
    conversation_id = conversation.id
    user_id = user.id
    current_adapter_key = run.adapter_key
    logger.info(
        "Queued agent run loaded: run_id=%s conversation_id=%s adapter=%s status=%s",
        run_id_value,
        conversation_id,
        current_adapter_key,
        run.status,
    )
    if run.status == "cancelled":
        return
    content = str(queued_payload.get("content") or "")
    model_id = queued_payload.get("modelId")
    skill_key = queued_payload.get("skillKey")
    run_started_at = run.created_at or datetime.now()
    assistant_messages: list[Message] = []
    assistant_output_parts: list[str] = []
    assistant_event_count = 0
    stage_bubble_counts: dict[str, int] = {}
    last_stage_bubble_key: str | None = None
    artifact_discovery_summary: dict[str, object] = {}
    adapter = None
    adapter_capacity_lease = None
    run_started_monotonic = asyncio.get_running_loop().time()
    model_runtime_config = model_runtime_config_builder.build_for_run(run)
    requested_runtime_adapter = current_adapter_key in {"hermes", "openclaw"}

    try:
        if (
            skill_key is None
            and not requested_runtime_adapter
            and model_runtime_config.supports_openai_chat_completions()
        ):
            await _complete_plain_chat_with_sensenova(db, run, conversation, content)
            return

        user_runtime_context = build_user_runtime_context(
            user,
            conversation_id,
            run_id=run_id_value,
            model_runtime_config=model_runtime_config,
        )
        run_workspace = run_workspace_dir(run_id_value, conversation_id, user_id)
        logger.info(
            "Resolving adapter for queued run: run_id=%s adapter=%s",
            run_id_value,
            current_adapter_key,
        )
        adapter_key, adapter = await resolve_adapter_for_model(
            db,
            user,
            model_id,
            adapter_key=current_adapter_key,
            conversation_id=conversation_id,
            run_id=run_id_value,
            model_runtime_config=model_runtime_config,
        )
        if await is_agent_run_cancelled(db, run_id_value):
            raise AgentRunCancelled()
        current_adapter_key = adapter_key or current_adapter_key
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
                "skillKey": skill_key,
                "adapterKey": current_adapter_key,
                "adapterLockScope": user_runtime_context.adapter_lock_scope(),
                "userRuntimeRoot": str(user_runtime_context.root_dir),
                "workspaceDir": str(run_workspace),
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
            skill_key=skill_key,
            model_id=model_id,
            run_id=run_id_value,
        )

        if hasattr(adapter, "stream_response_events") or hasattr(adapter, "stream_response"):
            stream = (
                adapter.stream_response_events(adapter_input)
                if hasattr(adapter, "stream_response_events")
                else adapter.stream_response(adapter_input)
            )
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
                    if (
                        skill_key is None
                        and not requested_runtime_adapter
                        and elapsed_seconds >= 45
                    ):
                        if hasattr(adapter, "cancel_run"):
                            await adapter.cancel_run(run_id_value)
                        raise AgentRunTimeout(
                            "plain_chat_timeout",
                            "Plain chat did not return a visible response within 45 seconds.",
                        )
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
                if skill_key is None and not requested_runtime_adapter:
                    break
        else:
            runtime_run = await adapter.create_run(adapter_input)
            if await is_agent_run_cancelled(db, run_id_value):
                raise AgentRunCancelled()
            message_content = (
                getattr(runtime_run, "output", None)
                or runtime_run.error
                or "Agent runtime did not return a response."
            )
            assistant_message = await persist_message(
                db,
                conversation_id,
                "assistant",
                message_content,
            )
            assistant_output_parts.append(message_content)
            assistant_messages.append(assistant_message)
            await record_db_agent_run_event(
                db,
                run,
                event_type="stage_update",
                label=message_content,
                status="running",
                progress=80,
                payload={"content": message_content, "messageId": assistant_message.id},
            )

        if await is_agent_run_cancelled(db, run_id_value):
            raise AgentRunCancelled()

        if skill_key is None and not requested_runtime_adapter and assistant_messages:
            assistant_message = assistant_messages[-1]
            await _complete_run(
                db,
                run,
                conversation_id,
                *(await _message_snapshot(db, assistant_message)),
            )
            return

        fresh_run = await db.get(AgentRun, run_id_value)
        if fresh_run is None:
            return
        run = fresh_run
        response_artifacts = await _discover_and_persist_artifacts(
            db,
            run,
            conversation_id,
            skill_key,
            run_started_at,
            adapter,
            artifact_discovery_summary,
            user_id,
            content,
            "\n\n".join(assistant_output_parts),
        )
        assistant_message = await _final_assistant_message(
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


async def _discover_and_persist_artifacts(
    db: AsyncSession,
    run: AgentRun,
    conversation_id: str,
    skill_key: str | None,
    run_started_at: datetime,
    adapter: object,
    artifact_discovery_summary: dict[str, object],
    user_id: str,
    content: str = "",
    assistant_output: str = "",
):
    run_id_value = run.id
    explicit_artifact_paths = (
        adapter.get_last_artifact_paths() if hasattr(adapter, "get_last_artifact_paths") else []
    )
    explicit_artifacts = (
        adapter.get_last_artifacts() if hasattr(adapter, "get_last_artifacts") else []
    )
    if explicit_artifacts:
        explicit_artifact_paths = [
            str(getattr(artifact, "path", ""))
            for artifact in explicit_artifacts
            if getattr(artifact, "path", "")
        ]
    event_path_candidates: list[str] = []
    result = await db.execute(select(AgentRunEvent).where(AgentRunEvent.run_id == run_id_value))
    for event in result.scalars().all():
        event_path_candidates.extend(extract_artifact_path_strings(event.payload or {}))
    for path in event_path_candidates:
        if path not in explicit_artifact_paths:
            explicit_artifact_paths.append(path)
    source_path_candidates = extract_artifact_path_strings(content)
    source_path_candidates.extend(
        path
        for path in extract_artifact_path_strings(assistant_output)
        if path not in source_path_candidates
    )
    related_source_artifact_paths = discover_related_artifact_paths(
        source_path_candidates,
        run_started_at,
    )
    for path in related_source_artifact_paths:
        if path not in explicit_artifact_paths:
            explicit_artifact_paths.append(path)
    artifact_discovery_summary.update(
        {
            "adapter_artifact_paths": list(explicit_artifact_paths),
            "source_artifact_paths": source_path_candidates,
            "related_source_artifact_paths": related_source_artifact_paths,
            "adapter_artifacts": [
                {
                    "artifact_path": getattr(artifact, "path", None),
                    "artifact_type": getattr(artifact, "artifact_type", None),
                    "run_id": getattr(artifact, "run_id", None),
                    "source_dir": getattr(artifact, "source_dir", None),
                    "title": getattr(artifact, "title", None),
                }
                for artifact in explicit_artifacts
            ],
        }
    )
    discovered_artifacts = await discover_artifacts_with_retry(
        conversation_id,
        run_started_at,
        explicit_artifact_paths,
        run_id_value,
        explicit_artifacts,
    )
    if (
        skill_key == "ppt_generation"
        and any(artifact.type == "html_page" for artifact in discovered_artifacts)
        and not any(artifact.type == "ppt_deck" for artifact in discovered_artifacts)
    ):
        try:
            pptx_artifact = create_pptx_from_html_artifacts(
                conversation_id,
                discovered_artifacts,
                run_id_value,
                settings.agent_run_ppt_export_timeout_seconds,
            )
            if pptx_artifact is not None:
                discovered_artifacts.append(pptx_artifact)
        except subprocess.TimeoutExpired as error:
            raise AgentRunTimeout(
                "ppt_export_timeout",
                f"PPTX export exceeded {settings.agent_run_ppt_export_timeout_seconds} seconds.",
            ) from error

    stored_artifacts = await persist_discovered_artifacts(
        db,
        conversation_id,
        discovered_artifacts,
        run_id_value,
    )
    current_run_artifacts = [
        artifact for artifact in stored_artifacts if artifact.run_id == run_id_value
    ]
    if not current_run_artifacts and assistant_output:
        fallback_artifact = create_markdown_artifact_from_content(
            conversation_id,
            assistant_output,
            run_id_value,
        )
        if fallback_artifact is not None:
            stored_artifacts.extend(
                await persist_discovered_artifacts(
                    db,
                    conversation_id,
                    [fallback_artifact],
                    run_id_value,
                )
            )
            current_run_artifacts = [
                artifact for artifact in stored_artifacts if artifact.run_id == run_id_value
            ]
    required_primary_types = PRIMARY_ARTIFACT_TYPES_BY_SKILL.get(skill_key or "")
    if required_primary_types and not any(
        artifact.type in required_primary_types for artifact in current_run_artifacts
    ):
        expected = ", ".join(sorted(required_primary_types))
        raise RuntimeError(
            f"{skill_key} completed without producing a primary artifact ({expected})."
        )
    if skill_key == "ppt_generation" and not current_run_artifacts:
        raise RuntimeError("PPT generation completed without producing any artifact.")
    if (
        skill_key == "ppt_generation"
        and any(artifact.type == "html_page" for artifact in current_run_artifacts)
        and not any(artifact.type == "ppt_deck" for artifact in current_run_artifacts)
    ):
        raise RuntimeError(
            "PPTX export did not produce a .pptx file. "
            "HTML pages were preserved as fallback artifacts."
        )
    developer_mode = await _user_developer_mode_by_id(db, user_id)
    visible_current_run_artifacts = [
        artifact
        for artifact in current_run_artifacts
        if developer_mode or not is_debug_artifact(artifact)
    ]
    visible_stored_artifacts = [
        artifact
        for artifact in stored_artifacts
        if developer_mode or not is_debug_artifact(artifact)
    ]
    response_artifacts = (
        visible_current_run_artifacts
        or sorted(
            visible_stored_artifacts,
            key=artifact_display_priority,
        )[-1:]
    )
    artifact_discovery_summary["stored_count"] = len(stored_artifacts)
    return response_artifacts


async def _final_assistant_message(
    db: AsyncSession,
    conversation_id: str,
    assistant_messages: list[Message],
    response_artifacts,
) -> Message:
    if assistant_messages:
        assistant_message = assistant_messages[-1]
        if response_artifacts:
            assistant_message.artifact_ids = [artifact.id for artifact in response_artifacts]
            await db.commit()
            await db.refresh(assistant_message)
        return assistant_message
    return await persist_message(
        db,
        conversation_id,
        "assistant",
        (
            "Agent runtime completed and generated artifacts."
            if response_artifacts
            else "Agent runtime completed without emitting a visible status update."
        ),
        [artifact.id for artifact in response_artifacts] or None,
    )


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
    if await is_agent_run_cancelled(db, run_id_value):
        await db.commit()
        return
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
