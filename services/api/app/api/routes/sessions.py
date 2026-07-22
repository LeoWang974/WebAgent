import asyncio
import json
import logging
import re
import subprocess
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
from app.api.routes.settings import user_developer_mode
from app.core.config import settings
from app.models import (
    AgentRun,
    AgentRunEvent,
    Artifact,
    Conversation,
    ConversationShare,
    FileAsset,
    Message,
)
from app.services import mock_store
from app.services.artifact_discovery import (
    create_artifacts_from_paths,
    create_artifacts_from_refs,
    create_pptx_from_html_artifacts,
    discover_artifact_paths_from_hermes_sessions,
    discover_artifacts_since,
    discover_related_artifact_paths,
)
from app.services.conversation_folders import (
    create_user_folder,
    delete_user_folder,
    get_owned_folder_or_404,
    list_user_folders,
    update_user_folder,
)
from app.services.persistence import (
    get_conversation_or_404,
    get_user_by_email,
    require_owner,
    to_artifact,
    to_message,
    to_session,
)
from app.services.runtime_context_builder import (
    build_runtime_content as build_skill_runtime_content,
)
from app.services.session_artifacts import (
    artifact_display_priority,
    is_debug_artifact,
    persist_discovered_artifacts,
    refresh_conversation,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class AgentRunCancelled(Exception):
    pass


class AgentRunTimeout(Exception):
    def __init__(self, timeout_type: str, message: str) -> None:
        self.timeout_type = timeout_type
        super().__init__(message)


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


def is_low_value_runtime_update(content: str, event_payload: dict) -> bool:
    normalized = re.sub(r"\s+", " ", content).strip().lower()
    if event_payload.get("rawActivityHeartbeat"):
        return True
    low_value_messages = {
        "openclaw cli task status: running.",
        "openclaw is still working; waiting for task progress.",
        "openclaw is still working; watching the report directory.",
        "openclaw is still working; waiting for report files.",
    }
    return normalized in low_value_messages


def resolve_skill_key(content: str, explicit_skill_key: str | None) -> str | None:
    if explicit_skill_key:
        return explicit_skill_key

    normalized = content.lower()
    html_generation_aliases = (
        "report-html-v2",
        "report html",
        "html report",
        "html文件",
        "输出html",
        "生成html",
        "生成 html",
        "输出 html",
    )
    if any(alias in normalized for alias in html_generation_aliases):
        return "html_generation"

    skill_aliases = [
        ("deep_research", ["sn-deep-research", "deep research", "深度调研", "调研", "研究报告"]),
        ("data_analysis", ["sn-da", "data analysis", "数据分析", "分析数据", "表格分析"]),
        ("ppt_generation", ["sn-ppt", "ppt", "幻灯片", "演示文稿"]),
        ("u1_image", ["u1", "生图", "生成图片", "图片生成"]),
    ]
    for skill_key, aliases in skill_aliases:
        if any(alias.lower() in normalized for alias in aliases):
            return skill_key
    return None


async def discover_artifacts_with_retry(
    session_id: str,
    since: datetime,
    explicit_artifact_paths: list[str],
    run_id: str | None,
    explicit_artifacts: list[object] | None = None,
) -> list[schemas.Artifact]:
    def dedupe_discovered_artifacts(
        artifacts: list[schemas.Artifact],
    ) -> list[schemas.Artifact]:
        deduped: list[schemas.Artifact] = []
        seen: set[str] = set()
        for artifact in artifacts:
            metadata = artifact.metadata or {}
            keys = [
                artifact.id,
                str(metadata.get("contentHash") or ""),
                str(metadata.get("normalizedPath") or ""),
                str(metadata.get("originalNormalizedPath") or ""),
                str(metadata.get("path") or ""),
                str(metadata.get("originalPath") or ""),
            ]
            present_keys = {item for item in keys if item}
            if present_keys & seen:
                continue
            seen.update(present_keys)
            deduped.append(artifact)
        return deduped

    def explicit_source_dirs() -> list[str]:
        source_dirs: list[str] = []
        for artifact_ref in explicit_artifacts or []:
            value = (
                artifact_ref.get("source_dir") or artifact_ref.get("sourceDir")
                if isinstance(artifact_ref, dict)
                else getattr(artifact_ref, "source_dir", None)
            )
            if isinstance(value, str) and value:
                source_dirs.append(value)
        return source_dirs

    for attempt in range(5):
        discovered_artifacts = create_artifacts_from_refs(
            session_id,
            explicit_artifacts or [],
            run_id,
        )
        if not discovered_artifacts:
            discovered_artifacts = create_artifacts_from_paths(
                session_id,
                explicit_artifact_paths,
                run_id,
            )
        if discovered_artifacts:
            related_paths = discover_related_artifact_paths(
                explicit_artifact_paths,
                since,
                source_dirs=explicit_source_dirs(),
            )
            if related_paths:
                discovered_artifacts.extend(
                    create_artifacts_from_paths(session_id, related_paths, run_id)
                )
                discovered_artifacts = dedupe_discovered_artifacts(discovered_artifacts)
        if not discovered_artifacts:
            session_artifact_paths = discover_artifact_paths_from_hermes_sessions(since)
            discovered_artifacts = create_artifacts_from_paths(
                session_id,
                session_artifact_paths,
                run_id,
            )
        if not discovered_artifacts:
            discovered_artifacts = discover_artifacts_since(session_id, since, run_id)
        if discovered_artifacts or attempt == 4:
            return dedupe_discovered_artifacts(discovered_artifacts)
        await asyncio.sleep(2)
    return []


async def is_agent_run_cancelled(db: AsyncSession, run_id: str) -> bool:
    result = await db.execute(select(AgentRun.status).where(AgentRun.id == run_id))
    return result.scalar_one_or_none() == "cancelled"


async def persist_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    artifact_ids: list[str] | None = None,
) -> Message:
    message = Message(
        conversation_id=session_id,
        role=role,
        content=content,
        artifact_ids=artifact_ids,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


@router.get("/folders", response_model=list[schemas.ConversationFolder])
async def list_conversation_folders(
    db: DbSession,
    current_user: CurrentUser,
) -> list[schemas.ConversationFolder]:
    return await list_user_folders(db, current_user.id)


@router.post("/folders", response_model=schemas.ConversationFolder)
async def create_conversation_folder(
    input_data: schemas.ConversationFolderCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.ConversationFolder:
    return await create_user_folder(db, current_user.id, input_data.name)


@router.patch("/folders/{folder_id}", response_model=schemas.ConversationFolder)
async def update_conversation_folder(
    folder_id: str,
    input_data: schemas.ConversationFolderUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.ConversationFolder:
    return await update_user_folder(db, folder_id, current_user.id, input_data.name)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_conversation_folder(
    folder_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    await delete_user_folder(db, folder_id, current_user.id)


@router.get("", response_model=list[schemas.Session])
async def list_sessions(
    db: DbSession,
    current_user: CurrentUser,
) -> list[schemas.Session]:
    result = await db.execute(
        select(Conversation)
        .outerjoin(ConversationShare, ConversationShare.conversation_id == Conversation.id)
        .where(
            or_(
                current_user.role == "admin",
                Conversation.user_id == current_user.id,
                Conversation.visibility == "public",
                (Conversation.visibility == "shared")
                & (ConversationShare.user_id == current_user.id),
            )
        )
        .options(selectinload(Conversation.shares).selectinload(ConversationShare.user))
        .order_by(Conversation.updated_at.desc())
    )
    conversations = result.scalars().unique().all()
    return [to_session(item) for item in conversations]


@router.post("", response_model=schemas.Session)
async def create_session(
    input_data: schemas.SessionCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.Session:
    if input_data.folder_id is not None:
        await get_owned_folder_or_404(db, input_data.folder_id, current_user.id)
    conversation = Conversation(
        folder_id=input_data.folder_id,
        user_id=current_user.id,
        title=input_data.title or "新对话",
        type=input_data.skill_key or "chat",
        pinned=False,
        status="active",
        visibility=input_data.visibility or "private",
    )
    db.add(conversation)
    await db.commit()
    conversation = await refresh_conversation(db, conversation.id)
    return to_session(conversation)


@router.patch("/{session_id}", response_model=schemas.Session)
async def update_session(
    session_id: str,
    input_data: schemas.SessionUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.Session:
    conversation = await get_conversation_or_404(db, session_id, current_user, require_write=True)
    require_owner(conversation, current_user)

    if input_data.pinned is not None:
        conversation.pinned = input_data.pinned
    if input_data.title is not None:
        conversation.title = input_data.title
    if "folder_id" in input_data.model_fields_set:
        if input_data.folder_id:
            await get_owned_folder_or_404(db, input_data.folder_id, current_user.id)
            conversation.folder_id = input_data.folder_id
        else:
            conversation.folder_id = None
    if input_data.visibility is not None:
        conversation.visibility = input_data.visibility
        if input_data.visibility == "private":
            for share in list(conversation.shares):
                await db.delete(share)

    if input_data.share_with_email:
        shared_user = await get_user_by_email(db, input_data.share_with_email)
        if shared_user is None:
            raise HTTPException(status_code=404, detail="Shared user is not registered")
        existing_share = next(
            (share for share in conversation.shares if share.user_id == shared_user.id),
            None,
        )
        if existing_share is None and shared_user.id != current_user.id:
            db.add(
                ConversationShare(
                    conversation_id=conversation.id,
                    user_id=shared_user.id,
                    role="viewer",
                )
            )
            conversation.visibility = "shared"

    if input_data.unshare_user_id:
        share_to_remove = next(
            (share for share in conversation.shares if share.user_id == input_data.unshare_user_id),
            None,
        )
        if share_to_remove is not None:
            await db.delete(share_to_remove)

    await db.commit()
    conversation = await refresh_conversation(db, session_id)
    return to_session(conversation)


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    conversation = await get_conversation_or_404(db, session_id, current_user)
    require_owner(conversation, current_user)
    run_ids_result = await db.execute(
        select(AgentRun.id).where(AgentRun.conversation_id == session_id)
    )
    run_ids = list(run_ids_result.scalars().all())
    if run_ids:
        await db.execute(delete(AgentRunEvent).where(AgentRunEvent.run_id.in_(run_ids)))

    await db.execute(delete(Artifact).where(Artifact.conversation_id == session_id))
    await db.execute(delete(FileAsset).where(FileAsset.conversation_id == session_id))
    await db.execute(delete(AgentRun).where(AgentRun.conversation_id == session_id))
    await db.delete(conversation)
    await db.commit()
    return None


@router.get("/{session_id}/messages", response_model=list[schemas.Message])
async def list_session_messages(
    session_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> list[schemas.Message]:
    await get_conversation_or_404(db, session_id, current_user)
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == session_id)
        .order_by(Message.created_at.asc())
    )
    return [to_message(item) for item in result.scalars().all()]


@router.post("/{session_id}/messages", response_model=schemas.SendMessageResult)
async def send_session_message(
    session_id: str,
    input_data: schemas.MessageCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.SendMessageResult:
    conversation = await get_conversation_or_404(db, session_id, current_user, require_write=True)
    resolved_skill_key = resolve_skill_key(input_data.content, input_data.skill_key)
    user_message = await persist_message(db, session_id, "user", input_data.content)

    assistant_content = "Agent runtime did not return a response."
    run = None

    try:
        from app.api.routes.agent_runs import (
            create_db_agent_run,
            finish_db_agent_run,
            record_db_agent_run_event,
            resolve_adapter_for_model,
        )

        adapter_key, adapter = await resolve_adapter_for_model(
            db,
            current_user,
            input_data.model_id,
        )
        runtime_content = await build_skill_runtime_content(
            db,
            session_id,
            input_data.content,
            resolved_skill_key,
            adapter_key,
        )
        run = await create_db_agent_run(
            db,
            session_id,
            title=resolved_skill_key or "Agent Run",
            status="running",
            progress=5,
            adapter_key=adapter_key,
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
                    content=runtime_content,
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
            from app.api.routes.agent_runs import finish_db_agent_run

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


@router.post("/{session_id}/messages/stream")
async def stream_session_message(
    session_id: str,
    input_data: schemas.MessageCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> StreamingResponse:
    await get_conversation_or_404(db, session_id, current_user, require_write=True)
    resolved_skill_key = resolve_skill_key(input_data.content, input_data.skill_key)

    async def event_stream():
        run_started_at = datetime.now()
        user_message = await persist_message(db, session_id, "user", input_data.content)
        yield sse("user_message", to_message(user_message).model_dump(by_alias=True))

        assistant_messages: list[Message] = []
        adapter = None
        run: AgentRun | None = None
        assistant_event_count = 0
        artifact_discovery_summary: dict[str, object] = {}
        short_chat_fast_closed = False
        run_started_monotonic = asyncio.get_running_loop().time()

        try:
            from app.api.routes.agent_runs import (
                create_db_agent_run,
                finish_db_agent_run,
                record_db_agent_run_event,
                resolve_adapter_for_model,
            )

            adapter_key, adapter = await resolve_adapter_for_model(
                db,
                current_user,
                input_data.model_id,
            )
            runtime_content = await build_skill_runtime_content(
                db,
                session_id,
                input_data.content,
                resolved_skill_key,
                adapter_key,
            )

            run = await create_db_agent_run(
                db,
                session_id,
                title=resolved_skill_key or "Agent Run",
                status="running",
                progress=5,
                adapter_key=adapter_key,
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
                    "skillKey": resolved_skill_key,
                    "adapterKey": adapter_key,
                },
            )

            if adapter is None:
                raise RuntimeError("No agent runtime adapter is available.")

            from agent_runtime.schemas import AgentRunCreate as AdapterAgentRunCreate

            adapter_input = AdapterAgentRunCreate(
                content=runtime_content,
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

                    if is_low_value_runtime_update(content, event_payload):
                        await record_db_agent_run_event(
                            db,
                            run,
                            event_type="raw_activity",
                            label=content,
                            status="running",
                            progress=progress or min(90, 10 + assistant_event_count * 8),
                            payload=event_payload,
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
                    if resolved_skill_key is None:
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

            if resolved_skill_key is None and assistant_messages:
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
                from app.api.routes.agent_runs import finish_db_agent_run

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
                from app.api.routes.agent_runs import finish_db_agent_run, record_db_agent_run_event

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
                from app.api.routes.agent_runs import finish_db_agent_run

                if adapter is not None and hasattr(adapter, "cancel_run"):
                    await adapter.cancel_run(run.id)
                await finish_db_agent_run(
                    db,
                    run,
                    status="disconnected",
                    label="Agent stream disconnected",
                    error="Agent stream disconnected before completion.",
                )
            raise
        except Exception as error:
            logger.exception("Agent stream failed")
            if run is not None and adapter is not None and hasattr(adapter, "cancel_run"):
                await adapter.cancel_run(run.id)
            if run is not None:
                from app.api.routes.agent_runs import finish_db_agent_run, record_db_agent_run_event

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

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{session_id}/artifacts", response_model=list[schemas.Artifact])
async def list_session_artifacts(
    session_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> list[schemas.Artifact]:
    await get_conversation_or_404(db, session_id, current_user)
    result = await db.execute(
        select(Artifact)
        .where(Artifact.conversation_id == session_id)
        .order_by(Artifact.created_at.desc())
    )
    developer_mode = await user_developer_mode(db, current_user)
    return [
        to_artifact(item)
        for item in result.scalars().all()
        if developer_mode or not is_debug_artifact(item)
    ]


@router.get("/{session_id}/files", response_model=list[schemas.FileAsset])
async def list_session_files(session_id: str) -> list[schemas.FileAsset]:
    return [item for item in mock_store.files if item.session_id == session_id]

