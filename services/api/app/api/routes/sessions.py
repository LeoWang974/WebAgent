import asyncio
import hashlib
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
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


def resolve_skill_key(content: str, explicit_skill_key: str | None) -> str | None:
    if explicit_skill_key:
        return explicit_skill_key

    normalized = content.lower()
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
            return discovered_artifacts
        await asyncio.sleep(2)
    return []


def is_primary_report_artifact(artifact: Artifact) -> bool:
    path = str((artifact.artifact_metadata or {}).get("path", "")).lower()
    title = artifact.title.lower()
    return artifact.type == "markdown_report" and (
        path.endswith("report.md")
        or path.endswith("final_report.md")
        or title in {"report", "final_report", "final-report"}
    )


def artifact_display_priority(artifact: Artifact) -> tuple[int, datetime]:
    type_priority = {
        "markdown_report": 10,
        "data_table": 20,
        "chart": 30,
        "html_page": 40,
        "ppt_deck": 80,
        "image_result": 90,
    }
    return (type_priority.get(artifact.type, 0), artifact.created_at)


def artifact_metadata_paths(metadata: dict) -> list[Path]:
    paths = []
    for key in ("path", "originalPath"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            paths.append(Path(value))
    return paths


def file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def artifact_content_hash(artifact: Artifact) -> str | None:
    metadata = dict(artifact.artifact_metadata or {})
    content_hash = metadata.get("contentHash")
    if isinstance(content_hash, str) and content_hash:
        return content_hash
    for path in artifact_metadata_paths(metadata):
        content_hash = file_sha256(path)
        if content_hash:
            metadata["contentHash"] = content_hash
            artifact.artifact_metadata = metadata
            return content_hash
    return None


def artifact_dedupe_keys(metadata: dict) -> tuple[str, list[str]]:
    content_hash = str(metadata.get("contentHash") or "")
    candidate_paths = [
        str(value)
        for value in {
            metadata.get("path"),
            metadata.get("originalPath"),
            metadata.get("normalizedPath"),
            metadata.get("originalNormalizedPath"),
        }
        if isinstance(value, str) and value
    ]
    return content_hash, candidate_paths


async def find_existing_artifact(
    db: AsyncSession,
    session_id: str,
    artifact_type: str,
    metadata: dict,
) -> Artifact | None:
    content_hash, candidate_paths = artifact_dedupe_keys(metadata)
    if content_hash:
        result = await db.execute(
            select(Artifact).where(
                Artifact.conversation_id == session_id,
                Artifact.artifact_metadata["contentHash"].as_string() == content_hash,
            )
        )
        existing_artifact = result.scalar_one_or_none()
        if existing_artifact is not None:
            return existing_artifact

    if candidate_paths:
        result = await db.execute(
            select(Artifact).where(
                Artifact.conversation_id == session_id,
                or_(
                    Artifact.artifact_metadata["path"].as_string().in_(candidate_paths),
                    Artifact.artifact_metadata["originalPath"].as_string().in_(candidate_paths),
                    Artifact.artifact_metadata["normalizedPath"].as_string().in_(candidate_paths),
                    Artifact.artifact_metadata["originalNormalizedPath"]
                    .as_string()
                    .in_(candidate_paths),
                ),
            )
        )
        existing_artifact = result.scalar_one_or_none()
        if existing_artifact is not None:
            return existing_artifact

    if content_hash:
        result = await db.execute(
            select(Artifact).where(
                Artifact.conversation_id == session_id,
                Artifact.type == artifact_type,
            )
        )
        for candidate_artifact in result.scalars().all():
            if artifact_content_hash(candidate_artifact) == content_hash:
                return candidate_artifact

    return None


async def refresh_conversation(db: AsyncSession, session_id: str) -> Conversation:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == session_id)
        .options(selectinload(Conversation.shares).selectinload(ConversationShare.user))
        .execution_options(populate_existing=True)
    )
    conversation = result.scalar_one()
    return conversation


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


async def persist_discovered_artifacts(
    db: AsyncSession,
    session_id: str,
    discovered_artifacts: list[schemas.Artifact],
    run_id: str | None = None,
) -> list[Artifact]:
    stored_artifacts: list[Artifact] = []

    for artifact_schema in discovered_artifacts:
        metadata = artifact_schema.metadata or {}
        existing_artifact = await find_existing_artifact(
            db,
            session_id,
            artifact_schema.type,
            metadata,
        )
        if existing_artifact is not None:
            stored_artifacts.append(existing_artifact)
            continue

        artifact = Artifact(
            conversation_id=session_id,
            run_id=run_id,
            type=artifact_schema.type,
            title=artifact_schema.title,
            status=artifact_schema.status,
            content=artifact_schema.content,
            artifact_metadata=artifact_schema.metadata,
        )
        db.add(artifact)
        stored_artifacts.append(artifact)

    if stored_artifacts:
        await db.commit()
        for artifact in stored_artifacts:
            await db.refresh(artifact)

    return stored_artifacts


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
    conversation = Conversation(
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
            response_artifacts = (
                current_run_artifacts
                or sorted(
                    stored_artifacts,
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
    return [to_artifact(item) for item in result.scalars().all()]


@router.get("/{session_id}/files", response_model=list[schemas.FileAsset])
async def list_session_files(session_id: str) -> list[schemas.FileAsset]:
    return [item for item in mock_store.files if item.session_id == session_id]
