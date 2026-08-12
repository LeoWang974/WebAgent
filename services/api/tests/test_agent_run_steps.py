from datetime import UTC, datetime

from app.models import AgentRunEvent
from app.services.agent_runs import _event_to_step


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
