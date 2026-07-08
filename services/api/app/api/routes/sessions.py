from fastapi import APIRouter, HTTPException

from app import schemas
from app.services import mock_store

router = APIRouter()


@router.get("", response_model=list[schemas.Session])
async def list_sessions() -> list[schemas.Session]:
    return sorted(mock_store.sessions, key=lambda item: item.updated_at, reverse=True)


@router.post("", response_model=schemas.Session)
async def create_session(input_data: schemas.SessionCreate) -> schemas.Session:
    session = schemas.Session(
        id=mock_store.new_id("session"),
        title=input_data.title or "New conversation",
        type=input_data.skill_key or "chat",
        pinned=False,
        status="active",
        updated_at=mock_store.now_iso(),
    )
    mock_store.sessions.insert(0, session)
    return session


@router.patch("/{session_id}", response_model=schemas.Session)
async def update_session(
    session_id: str,
    input_data: schemas.SessionUpdate,
) -> schemas.Session:
    session = next((item for item in mock_store.sessions if item.id == session_id), None)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    updated = session.model_copy(
        update={
            "pinned": input_data.pinned if input_data.pinned is not None else session.pinned,
            "title": input_data.title if input_data.title is not None else session.title,
            "updated_at": mock_store.now_iso(),
        }
    )
    mock_store.sessions[:] = [
        updated if item.id == session_id else item for item in mock_store.sessions
    ]
    return updated


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str) -> None:
    mock_store.sessions[:] = [item for item in mock_store.sessions if item.id != session_id]
    mock_store.messages[:] = [
        item for item in mock_store.messages if item.session_id != session_id
    ]
    mock_store.artifacts[:] = [
        item for item in mock_store.artifacts if item.session_id != session_id
    ]
    return None


@router.get("/{session_id}/messages", response_model=list[schemas.Message])
async def list_session_messages(session_id: str) -> list[schemas.Message]:
    return [item for item in mock_store.messages if item.session_id == session_id]


@router.post("/{session_id}/messages", response_model=schemas.SendMessageResult)
async def send_session_message(
    session_id: str,
    input_data: schemas.MessageCreate,
) -> schemas.SendMessageResult:
    session = next((item for item in mock_store.sessions if item.id == session_id), None)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    created_at = mock_store.now_iso()
    user_message = schemas.Message(
        id=mock_store.new_id("message_user"),
        session_id=session_id,
        role="user",
        content=input_data.content,
        created_at=created_at,
    )
    assistant_message = schemas.Message(
        id=mock_store.new_id("message_assistant"),
        session_id=session_id,
        role="assistant",
        content="Backend mock reply received. Real Agent Run and model gateway come next.",
        created_at=created_at,
    )
    mock_store.messages.extend([user_message, assistant_message])
    updated_session = session.model_copy(update={"updated_at": created_at, "status": "active"})
    mock_store.sessions[:] = [
        updated_session if item.id == session_id else item for item in mock_store.sessions
    ]
    return schemas.SendMessageResult(
        messages=[user_message, assistant_message],
        session=updated_session,
    )


@router.get("/{session_id}/artifacts", response_model=list[schemas.Artifact])
async def list_session_artifacts(session_id: str) -> list[schemas.Artifact]:
    return [item for item in mock_store.artifacts if item.session_id == session_id]


@router.get("/{session_id}/files", response_model=list[schemas.FileAsset])
async def list_session_files(session_id: str) -> list[schemas.FileAsset]:
    return [item for item in mock_store.files if item.session_id == session_id]
