from datetime import UTC, datetime

from app.models import AgentRunEvent
from app.services.agent_runs import AgentRunEventCursor, _event_to_step


def test_stage_step_uses_message_id_for_message_timing_recovery():
    event = AgentRunEvent(
        id="event-id",
        run_id="run-id",
        event_type="stage_started",
        payload={
            "messageId": "message-id",
            "step": {"label": "中文气泡验收通过", "status": "completed"},
        },
    )
    event.created_at = datetime(2026, 8, 9, 8, 18, 29, tzinfo=UTC)

    step = _event_to_step(event)

    assert step.id == "message-id"
    assert step.timestamp == "2026-08-09T08:18:29+00:00"


def test_agent_run_event_cursor_keeps_only_boundary_ids():
    first_timestamp = datetime(2026, 8, 9, 8, 18, 29, tzinfo=UTC)
    second_timestamp = datetime(2026, 8, 9, 8, 18, 30, tzinfo=UTC)
    first = AgentRunEvent(id="event-1", run_id="run-id", event_type="stage", payload={})
    second = AgentRunEvent(id="event-2", run_id="run-id", event_type="stage", payload={})
    late_at_same_timestamp = AgentRunEvent(
        id="event-0",
        run_id="run-id",
        event_type="stage",
        payload={},
    )
    later = AgentRunEvent(id="event-3", run_id="run-id", event_type="stage", payload={})
    first.created_at = first_timestamp
    second.created_at = first_timestamp
    late_at_same_timestamp.created_at = first_timestamp
    later.created_at = second_timestamp
    cursor = AgentRunEventCursor()

    assert cursor.consume([first, second]) == [first, second]
    assert cursor.consume([late_at_same_timestamp, first, second]) == [late_at_same_timestamp]
    assert cursor.consume([first, second, late_at_same_timestamp, later]) == [later]
    assert cursor.created_at == second_timestamp
    assert cursor.event_ids_at_timestamp == {"event-3"}
