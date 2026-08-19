# File purpose: Verifies test queued stream service behavior and its regression contracts.
# Main declarations: test_stream_dispatches_run_before_client_starts_reading verifies stream
# dispatches run before client starts reading.

from types import SimpleNamespace

import pytest

from app import schemas
from app.services import queued_stream_service


@pytest.mark.asyncio
async def test_stream_dispatches_run_before_client_starts_reading(monkeypatch) -> None:
    dispatched: list[str] = []
    user_message = SimpleNamespace(id="message-1")
    run = SimpleNamespace(id="run-1")

    async def fake_enqueue(db, session_id, input_data, current_user):
        del db, input_data, current_user
        dispatched.append(session_id)
        return user_message, run

    async def fake_stream():
        yield "event"

    def fake_stream_queued(db, session_id, prepared_message, prepared_run):
        del db
        assert session_id == "session-1"
        assert prepared_message is user_message
        assert prepared_run is run
        return fake_stream()

    monkeypatch.setattr(queued_stream_service, "enqueue_agent_run_message", fake_enqueue)
    monkeypatch.setattr(queued_stream_service, "stream_queued_agent_run", fake_stream_queued)

    stream = await queued_stream_service.stream_session_message_response(
        SimpleNamespace(),
        "session-1",
        schemas.MessageCreate(content="hello"),
        SimpleNamespace(id="user-1"),
    )

    assert dispatched == ["session-1"]
    assert [event async for event in stream] == ["event"]
