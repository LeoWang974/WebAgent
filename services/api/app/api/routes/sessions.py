import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import schemas
from app.db.session import get_db
from app.models import (
    AgentRun,
    AgentRunEvent,
    Artifact,
    Conversation,
    ConversationShare,
    FileAsset,
    Message,
    User,
)
from app.services import mock_store
from app.services.artifact_discovery import (
    create_artifacts_from_paths,
    discover_artifact_paths_from_hermes_sessions,
    discover_artifacts_since,
)
from app.services.persistence import (
    ensure_user,
    get_conversation_or_404,
    get_current_user,
    require_owner,
    to_artifact,
    to_message,
    to_session,
)

router = APIRouter()
logger = logging.getLogger(__name__)
AGENT_RUN_IDLE_TIMEOUT_SECONDS = 30 * 60


class AgentRunCancelled(Exception):
    pass


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
) -> list[schemas.Artifact]:
    for attempt in range(5):
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
        path = str((artifact_schema.metadata or {}).get("path", ""))
        original_path = str((artifact_schema.metadata or {}).get("originalPath", ""))
        existing_artifact = None
        if path:
            result = await db.execute(
                select(Artifact).where(
                    Artifact.conversation_id == session_id,
                    Artifact.artifact_metadata["path"].as_string() == path,
                )
            )
            existing_artifact = result.scalar_one_or_none()
        if existing_artifact is None and original_path:
            result = await db.execute(
                select(Artifact).where(
                    Artifact.conversation_id == session_id,
                    Artifact.artifact_metadata["originalPath"].as_string() == original_path,
                )
            )
            existing_artifact = result.scalar_one_or_none()
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[schemas.Session]:
    result = await db.execute(
        select(Conversation)
        .outerjoin(ConversationShare, ConversationShare.conversation_id == Conversation.id)
        .where(
            or_(
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
        shared_user = await ensure_user(db, input_data.share_with_email)
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> schemas.SendMessageResult:
    conversation = await get_conversation_or_404(db, session_id, current_user, require_write=True)
    resolved_skill_key = resolve_skill_key(input_data.content, input_data.skill_key)
    user_message = await persist_message(db, session_id, "user", input_data.content)

    assistant_content = "Agent runtime did not return a response."
    run = None

    try:
        from app.api.routes.agent_runs import (
            _get_adapter,
            create_db_agent_run,
            finish_db_agent_run,
            record_db_agent_run_event,
        )

        adapter = _get_adapter(input_data.model_id)
        run = await create_db_agent_run(
            db,
            session_id,
            title=resolved_skill_key or "Agent Run",
            status="running",
            progress=5,
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
                getattr(runtime_run, "output", None)
                or runtime_run.error
                or assistant_content
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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

        try:
            from app.api.routes.agent_runs import (
                _get_adapter,
                create_db_agent_run,
                finish_db_agent_run,
                record_db_agent_run_event,
            )

            adapter = _get_adapter(input_data.model_id)

            run = await create_db_agent_run(
                db,
                session_id,
                title=resolved_skill_key or "Agent Run",
                status="running",
                progress=5,
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
                },
            )

            if adapter is None:
                raise RuntimeError("No agent runtime adapter is available.")

            from agent_runtime.schemas import AgentRunCreate as AdapterAgentRunCreate

            adapter_input = AdapterAgentRunCreate(
                content=input_data.content,
                session_id=session_id,
                skill_key=resolved_skill_key,
                model_id=input_data.model_id,
                run_id=run.id,
            )

            if hasattr(adapter, "stream_response"):
                stream = adapter.stream_response(adapter_input)
                while True:
                    try:
                        chunk = await asyncio.wait_for(
                            stream.__anext__(),
                            timeout=AGENT_RUN_IDLE_TIMEOUT_SECONDS,
                        )
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError as error:
                        if hasattr(adapter, "cancel_run"):
                            await adapter.cancel_run(run.id)
                        raise TimeoutError(
                            f"Agent run timed out after {AGENT_RUN_IDLE_TIMEOUT_SECONDS} seconds without output."
                        ) from error

                    if await is_agent_run_cancelled(db, run.id):
                        raise AgentRunCancelled()

                    content = chunk.strip()
                    if not content:
                        continue

                    assistant_message = await persist_message(db, session_id, "assistant", content)
                    assistant_messages.append(assistant_message)
                    assistant_event_count += 1
                    progress = min(90, 10 + assistant_event_count * 8)
                    await record_db_agent_run_event(
                        db,
                        run,
                        event_type="stage_update",
                        label=content,
                        status="running",
                        progress=progress,
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

            explicit_artifact_paths = (
                adapter.get_last_artifact_paths()
                if hasattr(adapter, "get_last_artifact_paths")
                else []
            )
            discovered_artifacts = await discover_artifacts_with_retry(
                session_id,
                run_started_at,
                explicit_artifact_paths,
                run.id,
            )

            stored_artifacts = await persist_discovered_artifacts(
                db,
                session_id,
                discovered_artifacts,
                run.id,
            )

            if assistant_messages:
                assistant_message = assistant_messages[-1]
                if stored_artifacts:
                    assistant_message.artifact_ids = [artifact.id for artifact in stored_artifacts]
                    await db.commit()
                    await db.refresh(assistant_message)
            else:
                assistant_message = await persist_message(
                    db,
                    session_id,
                    "assistant",
                    (
                        "Hermes completed and generated artifacts."
                        if stored_artifacts
                        else "Hermes completed without emitting a visible status update."
                    ),
                    [artifact.id for artifact in stored_artifacts] or None,
                )

            ordered_artifacts = sorted(stored_artifacts, key=is_primary_report_artifact)
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
        except asyncio.CancelledError:
            if run is not None:
                from app.api.routes.agent_runs import finish_db_agent_run

                if adapter is not None and hasattr(adapter, "cancel_run"):
                    await adapter.cancel_run(run.id)
                await finish_db_agent_run(
                    db,
                    run,
                    status="cancelled",
                    label="Agent stream disconnected",
                )
            raise
        except Exception as error:
            logger.exception("Agent stream failed")
            if run is not None and adapter is not None and hasattr(adapter, "cancel_run"):
                await adapter.cancel_run(run.id)
            if run is not None:
                from app.api.routes.agent_runs import finish_db_agent_run

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
                },
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{session_id}/artifacts", response_model=list[schemas.Artifact])
async def list_session_artifacts(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
