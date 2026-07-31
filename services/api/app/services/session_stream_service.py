import asyncio
import json
import logging
import re
import subprocess
from datetime import datetime

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api.dependencies import CurrentUser
from app.api.routes.settings import is_runtime_adapter_model, user_developer_mode
from app.core.config import settings
from app.models import AgentRun, AgentRunEvent, Artifact, Message, ModelConfig
from app.services.adapter_limiter import acquire_adapter_capacity
from app.services.agent_runtime_context import build_user_runtime_context
from app.services.artifact_discovery import (
    create_pptx_from_html_artifacts,
    discover_artifacts_with_retry,
)
from app.services.model_runtime_config import ADAPTER_MODEL_ALIASES, model_runtime_config_builder
from app.services.persistence import (
    get_conversation_or_404,
    persist_message,
    to_artifact,
    to_message,
    to_session,
)
from app.services.session_artifacts import (
    artifact_display_priority,
    is_debug_artifact,
    persist_discovered_artifacts,
    refresh_conversation,
)
from app.services.session_message_service import resolve_skill_key

logger = logging.getLogger(__name__)
MODEL_CONFIG_DIRECTIVE_RE = re.compile(
    r"(?:~?/\.hermes/config\.yaml|model:\s*)",
    re.IGNORECASE,
)
PLACEHOLDER_API_KEYS = {"sk-xxx", "sk-test", "sk-smoke", "xxx", "your-api-key"}


class AgentRunCancelled(Exception):
    pass


class AgentRunTimeout(Exception):
    def __init__(self, timeout_type: str, message: str) -> None:
        self.timeout_type = timeout_type
        super().__init__(message)


def parse_model_config_directive(content: str) -> dict[str, str] | None:
    if not MODEL_CONFIG_DIRECTIVE_RE.search(content):
        return None

    values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip().lower().replace("-", "_")
        if normalized_key not in {"default", "provider", "base_url", "api_key"}:
            continue
        cleaned_value = value.strip().strip("'\"")
        if cleaned_value:
            values[normalized_key] = cleaned_value

    required = {"default", "base_url", "api_key"}
    if not required.issubset(values):
        return None
    if values["api_key"].strip().lower() in PLACEHOLDER_API_KEYS:
        raise HTTPException(
            status_code=400,
            detail="API key is a placeholder. Please provide a valid key before saving.",
        )
    values.setdefault("provider", "custom")
    return values


async def apply_model_config_directive(
    db: AsyncSession,
    current_user,
    model_id: str | None,
    values: dict[str, str],
) -> ModelConfig:
    model: ModelConfig | None = None
    if model_id and model_id not in ADAPTER_MODEL_ALIASES:
        result = await db.execute(
            select(ModelConfig).where(
                ModelConfig.id == model_id,
                ModelConfig.user_id == current_user.id,
            )
        )
        model = result.scalar_one_or_none()
        if model is not None and is_runtime_adapter_model(model):
            model = None

    if model is None:
        result = await db.execute(
            select(ModelConfig)
            .where(
                ModelConfig.user_id == current_user.id,
                ModelConfig.is_default.is_(True),
            )
            .order_by(ModelConfig.is_default.desc(), ModelConfig.updated_at.desc())
        )
        model = next(
            (item for item in result.scalars().all() if not is_runtime_adapter_model(item)),
            None,
        )

    if model is None:
        model = ModelConfig(
            user_id=current_user.id,
            name=values["default"],
            provider="custom",
            is_default=True,
            is_available=True,
        )
        db.add(model)

    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.user_id == current_user.id,
            ModelConfig.id != model.id,
        )
    )
    for item in result.scalars().all():
        item.is_default = False

    model.name = values["default"]
    model.provider = values.get("provider", "custom")
    model.base_url = values["base_url"]
    model.encrypted_api_key = values["api_key"]
    model.is_default = True
    model.is_available = True

    await db.commit()
    await db.refresh(model)
    return model


def runtime_diagnostics(adapter: object, artifact_discovery_summary: dict[str, object]) -> dict:
    diagnostics = (
        adapter.get_last_diagnostics()
        if adapter is not None and hasattr(adapter, "get_last_diagnostics")
        else {}
    )
    return {
        "artifactDiscovery": artifact_discovery_summary,
        "runtimeDiagnostics": diagnostics,
        "hermesDiagnostics": diagnostics,
    }


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def normalize_runtime_update(content: str) -> str:
    return re.sub(r"\s+", " ", content).strip().lower()


def runtime_stage_key(content: str, event_payload: dict) -> str:
    if event_payload.get("rawActivityHeartbeat"):
        return "heartbeat"
    normalized = normalize_runtime_update(content)
    stage_patterns = [
        ("complete", ("完成", "已生成", "completed", "succeeded", "done")),
        ("export", ("导出", "转换", "pptx", "export")),
        ("verify", ("验证", "校验", "检查", "validate", "verify")),
        ("write", ("写作", "撰写", "生成报告", "markdown 报告", "write report", "writing")),
        ("plan", ("规划", "大纲", "计划", "outline", "plan")),
        ("fetch", ("抓取", "网页", "fetch", "crawl", "browser")),
        ("search", ("搜索", "serper", "search")),
        ("file_io", ("读取相关文件", "写入中间文件", "查找相关文件", "read_file", "write_file")),
    ]
    for key, markers in stage_patterns:
        if any(marker in normalized for marker in markers):
            return key
    return f"message:{normalized[:96]}"


def is_low_value_runtime_update(content: str, event_payload: dict) -> bool:
    normalized = normalize_runtime_update(content)
    if event_payload.get("rawActivityHeartbeat"):
        return True
    low_value_messages = {
        "hermes is still running; raw output is being received.",
        "openclaw cli task status: running.",
        "openclaw cli task is running.",
        "openclaw is still working; waiting for task progress.",
        "openclaw is still working; watching the report directory.",
        "openclaw is still working; waiting for report files.",
        "正在读取相关文件...",
        "正在写入中间文件...",
        "正在查找相关文件和产物...",
        "正在准备任务配置文件...",
    }
    return normalized in low_value_messages


def should_suppress_stage_bubble(
    content: str,
    event_payload: dict,
    stage_counts: dict[str, int],
    last_stage_key: str | None,
) -> tuple[bool, str]:
    stage_key = runtime_stage_key(content, event_payload)
    if is_low_value_runtime_update(content, event_payload):
        return True, stage_key
    protocol = str(event_payload.get("protocol") or "")
    event_type = str(
        event_payload.get("hermesEventType") or event_payload.get("openclawEventType") or ""
    )
    if protocol and event_type in {
        "stage_started",
        "tool_call",
        "artifact_found",
        "completed",
    }:
        stage_counts[stage_key] = stage_counts.get(stage_key, 0) + 1
        return False, stage_key
    if stage_key == last_stage_key and stage_key not in {"complete", "export"}:
        return True, stage_key
    count = stage_counts.get(stage_key, 0)
    stage_counts[stage_key] = count + 1
    repeat_limits = {
        "search": 2,
        "fetch": 2,
        "plan": 2,
        "write": 3,
        "verify": 2,
        "export": 3,
        "file_io": 0,
    }
    limit = repeat_limits.get(stage_key)
    return limit is not None and count >= limit, stage_key


async def is_agent_run_cancelled(db: AsyncSession, run_id: str) -> bool:
    result = await db.execute(select(AgentRun.status).where(AgentRun.id == run_id))
    return result.scalar_one_or_none() == "cancelled"


async def enqueue_agent_run_message(
    db: AsyncSession,
    session_id: str,
    input_data: schemas.MessageCreate,
    current_user,
    resolved_skill_key: str | None,
):
    from app.services.agent_runs import (
        create_db_agent_run,
        record_db_agent_run_event,
        resolve_adapter_for_model,
    )
    from app.workers.agent_run_tasks import execute_agent_run_task

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
    execute_agent_run_task.apply_async((run.id,), queue=settings.agent_run_queue_name)
    return user_message, run


async def stream_queued_agent_run(
    db: AsyncSession,
    session_id: str,
    input_data: schemas.MessageCreate,
    current_user,
    resolved_skill_key: str | None,
):
    from app.services.agent_runs import TERMINAL_RUN_STATUSES

    user_message, run = await enqueue_agent_run_message(
        db,
        session_id,
        input_data,
        current_user,
        resolved_skill_key,
    )
    yield f": {' ' * 2048}\n\n"
    yield sse("user_message", to_message(user_message).model_dump(by_alias=True))
    yield sse(
        "run_started",
        {
            "runId": run.id,
            "sessionId": session_id,
            "status": run.status,
            "progress": run.progress,
        },
    )

    sent_event_ids: set[str] = set()
    assistant_done_sent = False
    run_id = run.id
    while True:
        db.expire_all()
        run = await db.get(AgentRun, run_id)
        if run is None:
            raise RuntimeError("Queued agent run disappeared before completion.")
        result = await db.execute(
            select(AgentRunEvent)
            .where(AgentRunEvent.run_id == run.id)
            .order_by(AgentRunEvent.created_at.asc())
        )
        events = result.scalars().all()
        for event in events:
            if event.id in sent_event_ids:
                continue
            sent_event_ids.add(event.id)
            payload = event.payload or {}
            if (
                event.event_type != "queued"
                and payload.get("content")
                and payload.get("messageId")
            ):
                yield sse(
                    "assistant_delta",
                    {
                        "content": payload["content"],
                        "messageId": payload["messageId"],
                        "sessionId": session_id,
                        "runId": run.id,
                    },
                )
            if event.event_type == "artifact_created" and isinstance(payload.get("artifact"), dict):
                yield sse(
                    "artifact_created",
                    {
                        "artifact": payload["artifact"],
                        "messageId": payload.get("messageId"),
                        "sessionId": session_id,
                        "runId": run.id,
                    },
                )
            if event.event_type == "assistant_done":
                done_payload = dict(payload)
                if "message" not in done_payload and payload.get("messageId"):
                    message = await db.get(Message, payload["messageId"])
                    if message is not None:
                        done_payload["message"] = to_message(message).model_dump(by_alias=True)
                if "session" not in done_payload:
                    conversation = await refresh_conversation(db, session_id)
                    done_payload["session"] = to_session(conversation).model_dump(by_alias=True)
                done_payload.setdefault("runId", run.id)
                done_payload.setdefault("status", run.status)
                yield sse("assistant_done", done_payload)
                assistant_done_sent = True

        if run.status in TERMINAL_RUN_STATUSES:
            if not assistant_done_sent:
                message_result = await db.execute(
                    select(Message)
                    .where(Message.conversation_id == session_id, Message.role == "assistant")
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
                message = message_result.scalar_one_or_none()
                if message is not None:
                    conversation = await refresh_conversation(db, session_id)
                    yield sse(
                        "assistant_done",
                        {
                            "message": to_message(message).model_dump(by_alias=True),
                            "session": to_session(conversation).model_dump(by_alias=True),
                            "runId": run.id,
                            "status": run.status,
                        },
                    )
            break
        yield ": heartbeat\n\n"
        await asyncio.sleep(settings.agent_run_event_poll_interval_seconds)



async def stream_session_message_response(
    session_id: str,
    input_data: schemas.MessageCreate,
    db: AsyncSession,
    current_user: CurrentUser,
) -> StreamingResponse:
    await get_conversation_or_404(db, session_id, current_user, require_write=True)
    resolved_skill_key = resolve_skill_key(input_data.content, input_data.skill_key)
    requested_runtime_adapter = input_data.adapter_key in {"hermes", "openclaw"}
    if settings.agent_run_queue_enabled and (
        resolved_skill_key is not None or requested_runtime_adapter
    ):
        return StreamingResponse(
            stream_queued_agent_run(db, session_id, input_data, current_user, resolved_skill_key),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    async def event_stream():
        run_started_at = datetime.now()
        user_message = await persist_message(db, session_id, "user", input_data.content)
        yield sse("user_message", to_message(user_message).model_dump(by_alias=True))

        assistant_messages: list[Message] = []
        adapter = None
        adapter_capacity_lease = None
        run: AgentRun | None = None
        assistant_event_count = 0
        stage_bubble_counts: dict[str, int] = {}
        last_stage_bubble_key: str | None = None
        artifact_discovery_summary: dict[str, object] = {}
        short_chat_fast_closed = False
        run_started_monotonic = asyncio.get_running_loop().time()

        try:
            from app.services.agent_run_executor import _complete_plain_chat_with_sensenova
            from app.services.agent_runs import (
                create_db_agent_run,
                finish_db_agent_run,
                record_db_agent_run_event,
                resolve_adapter_for_model,
            )

            requested_runtime_adapter = input_data.adapter_key in {
                "hermes",
                "openclaw",
            }
            model_config_values = parse_model_config_directive(input_data.content)
            if model_config_values is not None:
                model = await apply_model_config_directive(
                    db,
                    current_user,
                    input_data.model_id,
                    model_config_values,
                )
                conversation = await refresh_conversation(db, session_id)
                conversation.status = "active"
                reply = (
                    "模型配置已更新：当前默认模型为 "
                    f"`{model.name}`，base_url 为 `{model.base_url}`。"
                    "后续 Hermes Agent 运行会使用这组模型配置；你也可以在设置页切回 SenseNova。"
                )
                assistant_message = await persist_message(db, session_id, "assistant", reply)
                await db.commit()
                conversation = await refresh_conversation(db, session_id)
                yield sse(
                    "assistant_done",
                    {
                        "message": to_message(assistant_message).model_dump(by_alias=True),
                        "session": to_session(conversation).model_dump(by_alias=True),
                        "runId": None,
                        "status": "completed",
                    },
                )
                return

            model_runtime_config = await model_runtime_config_builder.build_for_user(
                db,
                current_user,
                input_data.model_id,
            )
            if (
                resolved_skill_key is None
                and not requested_runtime_adapter
                and model_runtime_config.supports_openai_chat_completions()
            ):
                run = await create_db_agent_run(
                    db,
                    session_id,
                    title="Plain Chat",
                    status="running",
                    progress=5,
                    adapter_key="sensenova",
                    model_runtime_config=model_runtime_config,
                )
                yield sse(
                    "run_started",
                    {
                        "runId": run.id,
                        "sessionId": session_id,
                        "status": run.status,
                        "progress": run.progress,
                    },
                )
                conversation = await refresh_conversation(db, session_id)
                await _complete_plain_chat_with_sensenova(db, run, conversation, input_data.content)
                result = await db.execute(
                    select(AgentRunEvent)
                    .where(AgentRunEvent.run_id == run.id)
                    .order_by(AgentRunEvent.created_at.asc())
                )
                for event in result.scalars().all():
                    payload = event.payload or {}
                    if payload.get("content") and payload.get("messageId"):
                        yield sse(
                            "assistant_delta",
                            {
                                "content": payload["content"],
                                "messageId": payload["messageId"],
                                "sessionId": session_id,
                                "runId": run.id,
                            },
                        )
                    if event.event_type == "assistant_done":
                        done_payload = dict(payload)
                        if "message" not in done_payload and payload.get("messageId"):
                            message = await db.get(Message, payload["messageId"])
                            if message is not None:
                                done_payload["message"] = to_message(message).model_dump(
                                    by_alias=True
                                )
                        if "session" not in done_payload:
                            conversation = await refresh_conversation(db, session_id)
                            done_payload["session"] = to_session(conversation).model_dump(
                                by_alias=True
                            )
                        done_payload.setdefault("runId", run.id)
                        done_payload.setdefault("status", run.status)
                        yield sse("assistant_done", done_payload)
                return

            if resolved_skill_key is None and not requested_runtime_adapter:
                run = await create_db_agent_run(
                    db,
                    session_id,
                    title="Plain Chat",
                    status="running",
                    progress=5,
                    adapter_key="direct_chat",
                    model_runtime_config=model_runtime_config,
                )
                yield sse(
                    "run_started",
                    {
                        "runId": run.id,
                        "sessionId": session_id,
                        "status": run.status,
                        "progress": run.progress,
                    },
                )
                assistant_content = (
                    f"当前模型 `{model_runtime_config.model_name}` 缺少可用的 API Key "
                    "或 base_url，无法进行普通短对话。请在设置页为该模型补齐配置，"
                    "或切回已经配置好的模型。"
                )
                assistant_message = await persist_message(
                    db,
                    session_id,
                    "assistant",
                    assistant_content,
                )
                conversation = await refresh_conversation(db, session_id)
                conversation.status = "active"
                await finish_db_agent_run(
                    db,
                    run,
                    status="failed",
                    label="Plain chat model configuration is incomplete",
                    error=assistant_content,
                )
                await db.commit()
                conversation = await refresh_conversation(db, session_id)
                yield sse(
                    "assistant_done",
                    {
                        "message": to_message(assistant_message).model_dump(by_alias=True),
                        "session": to_session(conversation).model_dump(by_alias=True),
                        "runId": run.id,
                        "status": "failed",
                    },
                )
                return

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
            yield sse(
                "run_started",
                {
                    "runId": run.id,
                    "sessionId": session_id,
                    "status": run.status,
                    "progress": run.progress,
                },
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
                raise RuntimeError("No agent runtime adapter is available.")

            user_runtime_context = build_user_runtime_context(
                current_user,
                session_id,
                run_id=run.id,
                model_runtime_config=model_runtime_config,
            )
            adapter_capacity_lease = await acquire_adapter_capacity(
                adapter_key,
                run.id,
                scope=user_runtime_context.adapter_lock_scope(),
            )
            await adapter_capacity_lease.__aenter__()
            await record_db_agent_run_event(
                db,
                run,
                event_type="adapter_capacity_acquired",
                label=f"Acquired {adapter_key or 'agent'} adapter capacity.",
                status="running",
                progress=run.progress,
                payload={
                    "adapterKey": adapter_key,
                    "adapterLockScope": user_runtime_context.adapter_lock_scope(),
                    "userRuntimeRoot": str(user_runtime_context.root_dir),
                },
            )
            if await is_agent_run_cancelled(db, run.id):
                raise AgentRunCancelled()

            from agent_runtime.schemas import AgentRunCreate as AdapterAgentRunCreate

            adapter_input = AdapterAgentRunCreate(
                content=input_data.content,
                session_id=session_id,
                skill_key=resolved_skill_key,
                model_id=input_data.model_id,
                run_id=run.id,
            )

            if hasattr(adapter, "stream_response_events") or hasattr(adapter, "stream_response"):
                stream = (
                    adapter.stream_response_events(adapter_input)
                    if hasattr(adapter, "stream_response_events")
                    else adapter.stream_response(adapter_input)
                )
                while True:
                    elapsed_seconds = asyncio.get_running_loop().time() - run_started_monotonic
                    overall_remaining = settings.agent_run_overall_timeout_seconds - elapsed_seconds
                    if overall_remaining <= 0:
                        if hasattr(adapter, "cancel_run"):
                            await adapter.cancel_run(run.id)
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
                        chunk = await asyncio.wait_for(
                            stream.__anext__(),
                            timeout=wait_timeout,
                        )
                    except StopAsyncIteration:
                        break
                    except TimeoutError as error:
                        if hasattr(adapter, "cancel_run"):
                            await adapter.cancel_run(run.id)
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

                    if await is_agent_run_cancelled(db, run.id):
                        raise AgentRunCancelled()

                    if hasattr(chunk, "step"):
                        step = getattr(chunk, "step", None)
                        content = str(getattr(step, "label", "") or "").strip()
                        event_type = str(getattr(chunk, "event_type", "stage_update"))
                        event_payload = dict(getattr(chunk, "payload", {}) or {})
                        progress = int(getattr(chunk, "progress", 0) or 0)
                    else:
                        content = str(chunk).strip()
                        event_type = "stage_update"
                        event_payload = {}
                        progress = 0
                    if not content:
                        continue

                    should_suppress, stage_key = should_suppress_stage_bubble(
                        content,
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
                            label=content,
                            status="running",
                            progress=progress or min(90, 10 + assistant_event_count * 8),
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
                            label=content,
                            status="running",
                            progress=progress or min(90, 10 + assistant_event_count * 8),
                            payload=event_payload,
                        )
                        continue

                    assistant_message = await persist_message(db, session_id, "assistant", content)
                    assistant_messages.append(assistant_message)
                    assistant_event_count += 1
                    progress = progress or min(90, 10 + assistant_event_count * 8)
                    await record_db_agent_run_event(
                        db,
                        run,
                        event_type=event_type,
                        label=content,
                        status="running",
                        progress=progress,
                        payload={
                            "content": content,
                            "messageId": assistant_message.id,
                            "stageKey": stage_key,
                            **event_payload,
                        },
                    )
                    yield sse(
                        "assistant_delta",
                        {
                            "content": content,
                            "messageId": assistant_message.id,
                            "sessionId": session_id,
                            "runId": run.id,
                        },
                    )
                    if resolved_skill_key is None and not requested_runtime_adapter:
                        short_chat_fast_closed = True
                        break
            else:
                runtime_run = await adapter.create_run(adapter_input)
                if await is_agent_run_cancelled(db, run.id):
                    raise AgentRunCancelled()
                content = (
                    getattr(runtime_run, "output", None)
                    or runtime_run.error
                    or "Agent runtime did not return a response."
                )
                assistant_message = await persist_message(db, session_id, "assistant", content)
                assistant_messages.append(assistant_message)
                await record_db_agent_run_event(
                    db,
                    run,
                    event_type="stage_update",
                    label=content,
                    status="running",
                    progress=80,
                    payload={
                        "content": content,
                        "messageId": assistant_message.id,
                    },
                )
                yield sse(
                    "assistant_delta",
                    {
                        "content": content,
                        "messageId": assistant_message.id,
                        "sessionId": session_id,
                        "runId": run.id,
                    },
                )

            if await is_agent_run_cancelled(db, run.id):
                raise AgentRunCancelled()

            if (
                resolved_skill_key is None
                and not requested_runtime_adapter
                and assistant_messages
            ):
                assistant_message = assistant_messages[-1]
                if short_chat_fast_closed:
                    await record_db_agent_run_event(
                        db,
                        run,
                        event_type="completed",
                        label="Short chat completed after first response",
                        status="running",
                        progress=95,
                        payload={
                            "messageId": assistant_message.id,
                            "shortChatFastClose": True,
                            "artifactDiscoverySkipped": True,
                        },
                    )
                conversation = await refresh_conversation(db, session_id)
                conversation.status = "active"
                await finish_db_agent_run(
                    db,
                    run,
                    status="completed",
                    label="Agent run completed",
                    output=assistant_message.content,
                )
                await db.commit()
                conversation = await refresh_conversation(db, session_id)
                yield sse(
                    "assistant_done",
                    {
                        "message": to_message(assistant_message).model_dump(by_alias=True),
                        "session": to_session(conversation).model_dump(by_alias=True),
                        "runId": run.id,
                        "status": "completed",
                    },
                )
                if hasattr(adapter, "cancel_run"):

                    async def cleanup_short_chat_run() -> None:
                        try:
                            await adapter.cancel_run(run.id)
                        except Exception as error:
                            logger.warning(
                                "Failed to cleanup short chat adapter run %s: %s",
                                run.id,
                                error,
                            )

                    asyncio.create_task(cleanup_short_chat_run())
                return

            explicit_artifact_paths = (
                adapter.get_last_artifact_paths()
                if hasattr(adapter, "get_last_artifact_paths")
                else []
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
            artifact_discovery_summary = {
                "adapter_artifact_paths": list(explicit_artifact_paths),
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
            discovered_artifacts = await discover_artifacts_with_retry(
                session_id,
                run_started_at,
                explicit_artifact_paths,
                run.id,
                explicit_artifacts,
            )
            artifact_discovery_summary["discovered_count"] = len(discovered_artifacts)
            artifact_discovery_summary["discovered_artifacts"] = [
                {
                    "id": artifact.id,
                    "title": artifact.title,
                    "type": artifact.type,
                    "metadata": artifact.metadata,
                }
                for artifact in discovered_artifacts
            ]
            if (
                resolved_skill_key == "ppt_generation"
                and any(artifact.type == "html_page" for artifact in discovered_artifacts)
                and not any(artifact.type == "ppt_deck" for artifact in discovered_artifacts)
            ):
                try:
                    pptx_artifact = create_pptx_from_html_artifacts(
                        session_id,
                        discovered_artifacts,
                        run.id,
                        settings.agent_run_ppt_export_timeout_seconds,
                    )
                    if pptx_artifact is not None:
                        discovered_artifacts.append(pptx_artifact)
                except subprocess.TimeoutExpired as error:
                    if hasattr(adapter, "cancel_run"):
                        await adapter.cancel_run(run.id)
                    raise AgentRunTimeout(
                        "ppt_export_timeout",
                        (
                            "PPTX export exceeded "
                            f"{settings.agent_run_ppt_export_timeout_seconds} seconds."
                        ),
                    ) from error

            stored_artifacts = await persist_discovered_artifacts(
                db,
                session_id,
                discovered_artifacts,
                run.id,
            )
            artifact_discovery_summary["stored_count"] = len(stored_artifacts)
            artifact_discovery_summary["stored_artifacts"] = [
                {
                    "id": artifact.id,
                    "run_id": artifact.run_id,
                    "title": artifact.title,
                    "type": artifact.type,
                }
                for artifact in stored_artifacts
            ]
            current_run_artifacts = [
                artifact for artifact in stored_artifacts if artifact.run_id == run.id
            ]
            developer_mode = await user_developer_mode(db, current_user)
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
            if (
                resolved_skill_key == "ppt_generation"
                and any(artifact.type == "html_page" for artifact in current_run_artifacts)
                and not any(artifact.type == "ppt_deck" for artifact in current_run_artifacts)
            ):
                raise RuntimeError(
                    "PPTX export did not produce a .pptx file. "
                    "HTML pages were preserved as fallback artifacts."
                )

            if assistant_messages:
                assistant_message = assistant_messages[-1]
                if response_artifacts:
                    assistant_message.artifact_ids = [
                        artifact.id for artifact in response_artifacts
                    ]
                    await db.commit()
                    await db.refresh(assistant_message)
            else:
                assistant_message = await persist_message(
                    db,
                    session_id,
                        "assistant",
                        (
                            "Agent runtime completed and generated artifacts."
                            if response_artifacts
                            else "Agent runtime completed without emitting a visible status update."
                        ),
                        [artifact.id for artifact in response_artifacts] or None,
                    )

            ordered_artifacts = sorted(response_artifacts, key=artifact_display_priority)
            for artifact in ordered_artifacts:
                await record_db_agent_run_event(
                    db,
                    run,
                    event_type="artifact_created",
                    label=f"Artifact created: {artifact.title}",
                    status="rendering",
                    progress=95,
                    payload={
                        "artifactId": artifact.id,
                        "artifactType": artifact.type,
                        "title": artifact.title,
                    },
                )
                yield sse(
                    "artifact_created",
                    {
                        "artifact": to_artifact(artifact).model_dump(by_alias=True),
                        "messageId": assistant_message.id,
                        "sessionId": session_id,
                        "runId": run.id,
                    },
                )

            conversation = await refresh_conversation(db, session_id)
            conversation.status = "active"
            await finish_db_agent_run(
                db,
                run,
                status="completed",
                label="Agent run completed",
                output=assistant_message.content,
            )
            await db.commit()
            conversation = await refresh_conversation(db, session_id)
            yield sse(
                "assistant_done",
                {
                    "message": to_message(assistant_message).model_dump(by_alias=True),
                    "session": to_session(conversation).model_dump(by_alias=True),
                    "runId": run.id,
                },
            )
        except AgentRunCancelled:
            if run is not None:
                from app.services.agent_runs import finish_db_agent_run

                await finish_db_agent_run(
                    db,
                    run,
                    status="cancelled",
                    label="Agent run cancelled",
                )
            conversation = await refresh_conversation(db, session_id)
            conversation.status = "active"
            await db.commit()
            conversation = await refresh_conversation(db, session_id)
            cancelled_message = await persist_message(
                db,
                session_id,
                "assistant",
                "任务已取消。",
            )
            yield sse(
                "assistant_done",
                {
                    "message": to_message(cancelled_message).model_dump(by_alias=True),
                    "session": to_session(conversation).model_dump(by_alias=True),
                    "runId": run.id if run is not None else None,
                    "status": "cancelled",
                },
            )
        except AgentRunTimeout as error:
            logger.warning("Agent stream timed out: %s", error)
            if run is not None:
                from app.services.agent_runs import finish_db_agent_run, record_db_agent_run_event

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
            timeout_message = await persist_message(
                db,
                session_id,
                "assistant",
                f"Agent runtime timeout: {error}",
            )
            conversation = await refresh_conversation(db, session_id)
            conversation.status = "failed"
            await db.commit()
            conversation = await refresh_conversation(db, session_id)
            yield sse(
                "assistant_done",
                {
                    "message": to_message(timeout_message).model_dump(by_alias=True),
                    "session": to_session(conversation).model_dump(by_alias=True),
                    "runId": run.id if run is not None else None,
                    "status": "failed",
                },
            )
        except asyncio.CancelledError:
            if run is not None:
                from app.services.agent_runs import finish_db_agent_run

                artifact_result = await db.execute(
                    select(Artifact.id)
                    .where(Artifact.run_id == run.id, Artifact.type != "debug_json")
                    .limit(1)
                )
                has_artifact = artifact_result.scalar_one_or_none() is not None
                latest_assistant_message = assistant_messages[-1] if assistant_messages else None
                if has_artifact:
                    await finish_db_agent_run(
                        db,
                        run,
                        status="completed",
                        label="Agent run completed after client disconnected",
                        output=(
                            latest_assistant_message.content
                            if latest_assistant_message is not None
                            else None
                        ),
                    )
                else:
                    if adapter is not None and hasattr(adapter, "cancel_run"):
                        await adapter.cancel_run(run.id)
                    await finish_db_agent_run(
                        db,
                        run,
                        status="disconnected",
                        label="Agent stream disconnected",
                        error="Agent stream disconnected before completion.",
                    )
                conversation = await refresh_conversation(db, session_id)
                conversation.status = "active"
                await db.commit()
            raise
        except Exception as error:
            logger.exception("Agent stream failed")
            if run is not None and adapter is not None and hasattr(adapter, "cancel_run"):
                await adapter.cancel_run(run.id)
            if run is not None:
                from app.services.agent_runs import finish_db_agent_run, record_db_agent_run_event

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
            error_message = await persist_message(
                db,
                session_id,
                "assistant",
                f"Agent runtime error: {error}",
            )
            conversation = await refresh_conversation(db, session_id)
            conversation.status = "failed"
            await db.commit()
            conversation = await refresh_conversation(db, session_id)
            yield sse(
                "assistant_done",
                {
                    "message": to_message(error_message).model_dump(by_alias=True),
                    "session": to_session(conversation).model_dump(by_alias=True),
                    "runId": run.id if run is not None else None,
                    "status": "failed",
                },
            )
        finally:
            if adapter_capacity_lease is not None:
                await adapter_capacity_lease.__aexit__(None, None, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


