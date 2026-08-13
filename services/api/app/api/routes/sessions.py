import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import selectinload

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
from app.models import (
    AgentRun,
    AgentRunEvent,
    Artifact,
    Conversation,
    ConversationShare,
    FileAsset,
    Message,
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
    to_file_asset,
    to_message,
    to_session,
)
from app.services.session_artifacts import (
    is_debug_artifact,
    refresh_conversation,
)
from app.services.session_message_service import send_message_core
from app.services.session_stream_service import stream_session_message_response
from app.services.settings_service import user_developer_mode

router = APIRouter()
logger = logging.getLogger(__name__)

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
        type="chat",
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
    return await send_message_core(db, conversation, input_data, current_user)


@router.post("/{session_id}/messages/stream")
async def stream_session_message(
    session_id: str,
    input_data: schemas.MessageCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> StreamingResponse:
    await get_conversation_or_404(db, session_id, current_user, require_write=True)
    stream = await stream_session_message_response(db, session_id, input_data, current_user)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
        to_artifact(item, include_payload=False)
        for item in result.scalars().all()
        if developer_mode or not is_debug_artifact(item)
    ]


@router.get("/{session_id}/files", response_model=list[schemas.FileAsset])
async def list_session_files(
    session_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> list[schemas.FileAsset]:
    await get_conversation_or_404(db, session_id, current_user)
    result = await db.execute(
        select(FileAsset)
        .where(FileAsset.conversation_id == session_id)
        .order_by(FileAsset.created_at.desc())
    )
    return [to_file_asset(item) for item in result.scalars().all()]
