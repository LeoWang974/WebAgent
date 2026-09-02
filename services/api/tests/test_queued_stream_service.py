# File purpose: Verifies test queued stream service behavior and its regression contracts.
# Main declarations: test_stream_dispatches_run_before_client_starts_reading verifies stream
# dispatches run before client starts reading; test_stream_falls_back_to_event_id_for_bubble
# verifies content without a persisted message id still reaches the browser.

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


@pytest.mark.asyncio
async def test_stream_falls_back_to_event_id_for_bubble(monkeypatch) -> None:
    run = SimpleNamespace(id="run-1", status="completed", progress=80)
    event = SimpleNamespace(
        id="event-1",
        event_type="stage_update",
        payload={"content": "Hermes reply without a message id"},
    )
    done_event = SimpleNamespace(
        id="event-2",
        event_type="assistant_done",
        payload={},
    )

    class Result:
        def scalar_one_or_none(self):
            return run

    class FakeDb:
        def __init__(self):
            self.rollback_count = 0

        async def execute(self, query):
            del query
            return Result()

        async def rollback(self):
            self.rollback_count += 1

    async def fake_events(db, run_id, cursor):
        del db, run_id, cursor
        return [event, done_event]

    async def fake_queue_payload(db, run_id):
        del db, run_id
        return {}

    monkeypatch.setattr(queued_stream_service, "_queued_event_payload", fake_queue_payload)
    monkeypatch.setattr(queued_stream_service, "list_new_run_events", fake_events)

    async def fake_done_payload(db, session_id, run, payload):
        del db, session_id, run, payload
        return {}

    monkeypatch.setattr(queued_stream_service, "build_assistant_done_payload", fake_done_payload)
    monkeypatch.setattr(
        queued_stream_service,
        "to_message",
        lambda message: SimpleNamespace(model_dump=lambda **kwargs: {"id": message.id}),
    )

    db = FakeDb()
    stream = queued_stream_service.stream_queued_agent_run(
        db,
        "session-1",
        SimpleNamespace(id="message-1"),
        run,
    )
    output = [item async for item in stream]

    assert any(item.startswith("event: assistant_delta") for item in output)
    assert any("run_event_run-1_event-1" in item for item in output)
    assert db.rollback_count >= 2
