import json
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import schemas
from app.services.artifact_discovery import (
    create_artifacts_from_paths,
    discover_artifacts_since,
)
from app.services import mock_store

router = APIRouter()
logger = logging.getLogger(__name__)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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

    assistant_content = "Agent runtime did not return a response."

    try:
        from agent_runtime.schemas import AgentRunCreate as AdapterAgentRunCreate
        from app.api.routes.agent_runs import _get_adapter

        adapter = _get_adapter(input_data.model_id)

        if adapter is not None:
            runtime_run = await adapter.create_run(
                AdapterAgentRunCreate(
                    content=input_data.content,
                    session_id=session_id,
                    skill_key=input_data.skill_key,
                    model_id=input_data.model_id,
                )
            )
            assistant_content = (
                getattr(runtime_run, "output", None)
                or runtime_run.error
                or assistant_content
            )
        else:
            assistant_content = "No agent runtime adapter is available."
    except Exception as error:
        assistant_content = f"Agent runtime error: {error}"

    assistant_message = schemas.Message(
        id=mock_store.new_id("message_assistant"),
        session_id=session_id,
        role="assistant",
        content=assistant_content,
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


@router.post("/{session_id}/messages/stream")
async def stream_session_message(
    session_id: str,
    input_data: schemas.MessageCreate,
) -> StreamingResponse:
    session = next((item for item in mock_store.sessions if item.id == session_id), None)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_stream():
        created_at = mock_store.now_iso()
        run_started_at = datetime.fromisoformat(created_at)

        user_message = schemas.Message(
            id=mock_store.new_id("message_user"),
            session_id=session_id,
            role="user",
            content=input_data.content,
            created_at=created_at,
        )
        mock_store.messages.append(user_message)
        yield sse("user_message", user_message.model_dump(by_alias=True))

        assistant_messages: list[schemas.Message] = []

        try:
            from agent_runtime.schemas import AgentRunCreate as AdapterAgentRunCreate
            from app.api.routes.agent_runs import _get_adapter

            adapter = _get_adapter(input_data.model_id)

            if adapter is None:
                raise RuntimeError("No agent runtime adapter is available.")

            adapter_input = AdapterAgentRunCreate(
                content=input_data.content,
                session_id=session_id,
                skill_key=input_data.skill_key,
                model_id=input_data.model_id,
            )

            if hasattr(adapter, "stream_response"):
                async for chunk in adapter.stream_response(adapter_input):
                    content = chunk.strip()
                    if not content:
                        continue

                    assistant_message = schemas.Message(
                        id=mock_store.new_id("message_assistant"),
                        session_id=session_id,
                        role="assistant",
                        content=content,
                        created_at=mock_store.now_iso(),
                    )
                    assistant_messages.append(assistant_message)
                    mock_store.messages.append(assistant_message)
                    yield sse(
                        "assistant_delta",
                        {
                            "content": content,
                            "messageId": assistant_message.id,
                            "sessionId": session_id,
                        },
                    )
            else:
                runtime_run = await adapter.create_run(adapter_input)
                content = (
                    getattr(runtime_run, "output", None)
                    or runtime_run.error
                    or "Agent runtime did not return a response."
                )
                assistant_message = schemas.Message(
                    id=mock_store.new_id("message_assistant"),
                    session_id=session_id,
                    role="assistant",
                    content=content,
                    created_at=mock_store.now_iso(),
                )
                assistant_messages.append(assistant_message)
                mock_store.messages.append(assistant_message)
                yield sse(
                    "assistant_delta",
                    {
                        "content": content,
                        "messageId": assistant_message.id,
                        "sessionId": session_id,
                    },
                )

            explicit_artifact_paths = (
                adapter.get_last_artifact_paths()
                if hasattr(adapter, "get_last_artifact_paths")
                else []
            )
            discovered_artifacts = create_artifacts_from_paths(
                session_id,
                explicit_artifact_paths,
            )
            if not discovered_artifacts:
                discovered_artifacts = discover_artifacts_since(session_id, run_started_at)
            if discovered_artifacts:
                mock_store.artifacts.extend(discovered_artifacts)

            if assistant_messages:
                assistant_message = assistant_messages[-1]
                if discovered_artifacts:
                    assistant_message = assistant_message.model_copy(
                        update={"artifact_ids": [artifact.id for artifact in discovered_artifacts]}
                    )
                    mock_store.messages[:] = [
                        assistant_message if item.id == assistant_message.id else item
                        for item in mock_store.messages
                    ]
            else:
                assistant_message = schemas.Message(
                    id=mock_store.new_id("message_assistant"),
                    session_id=session_id,
                    role="assistant",
                    content=(
                        "Hermes completed and generated artifacts."
                        if discovered_artifacts
                        else "Hermes completed without emitting a visible status update."
                    ),
                    created_at=mock_store.now_iso(),
                    artifact_ids=[artifact.id for artifact in discovered_artifacts] or None,
                )
                mock_store.messages.append(assistant_message)

            for artifact in discovered_artifacts:
                yield sse(
                    "artifact_created",
                    {
                        "artifact": artifact.model_dump(by_alias=True),
                        "messageId": assistant_message.id,
                        "sessionId": session_id,
                    },
                )

            updated_session = session.model_copy(
                update={"updated_at": mock_store.now_iso(), "status": "active"}
            )
            mock_store.sessions[:] = [
                updated_session if item.id == session_id else item
                for item in mock_store.sessions
            ]
            yield sse(
                "assistant_done",
                {
                    "message": assistant_message.model_dump(by_alias=True),
                    "session": updated_session.model_dump(by_alias=True),
                },
            )
        except Exception as error:
            error_message = schemas.Message(
                id=mock_store.new_id("message_assistant"),
                session_id=session_id,
                role="assistant",
                content=f"Agent runtime error: {error}",
                created_at=mock_store.now_iso(),
            )
            mock_store.messages.append(error_message)
            yield sse(
                "assistant_done",
                {
                    "message": error_message.model_dump(by_alias=True),
                    "session": session.model_dump(by_alias=True),
                },
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{session_id}/artifacts", response_model=list[schemas.Artifact])
async def list_session_artifacts(session_id: str) -> list[schemas.Artifact]:
    return [item for item in mock_store.artifacts if item.session_id == session_id]


@router.get("/{session_id}/files", response_model=list[schemas.FileAsset])
async def list_session_files(session_id: str) -> list[schemas.FileAsset]:
    return [item for item in mock_store.files if item.session_id == session_id]
