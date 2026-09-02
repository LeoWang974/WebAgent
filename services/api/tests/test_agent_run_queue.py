# File purpose: Verifies content-independent Agent Run queueing and cancellation polling.
# Main declarations: queue routing and persisted-message tests protect prompt transparency;
# cancellation polling test verifies database-read throttling.

from types import SimpleNamespace

import pytest

from app.services import agent_run_control
from app.services.agent_run_control import AgentRunCancellationPoller
from app.services.agent_run_executor import _queued_user_content
from app.services.agent_run_queue import queue_for_message


def test_all_prompts_use_the_same_hermes_queue():
    assert queue_for_message() == ("agent-runs", "Hermes 任务队列")


@pytest.mark.asyncio
async def test_worker_loads_the_exact_persisted_user_message():
    original = "  第一行\n\n第二行，保留空白。  "
    message = SimpleNamespace(
        content=original,
        conversation_id="conversation-1",
        role="user",
    )

    class FakeDb:
        async def get(self, model, message_id):
            del model
            assert message_id == "message-1"
            return message

    content = await _queued_user_content(
        FakeDb(),
        "conversation-1",
        {"userMessageId": "message-1"},
    )

    assert content == original


@pytest.mark.asyncio
async def test_worker_supports_legacy_queued_prompt_payloads():
    original = " legacy prompt "
    content = await _queued_user_content(
        SimpleNamespace(),
        "conversation-1",
        {"content": original},
    )

    assert content == original


@pytest.mark.asyncio
async def test_cancellation_poller_throttles_negative_database_reads(monkeypatch):
    calls = 0

    async def fake_is_cancelled(db, run_id):
        nonlocal calls
        del db, run_id
        calls += 1
        return False

    monkeypatch.setattr(agent_run_control, "is_agent_run_cancelled", fake_is_cancelled)
    poller = AgentRunCancellationPoller(interval_seconds=60)
    db = SimpleNamespace()

    assert await poller.is_cancelled(db, "run-1") is False
    assert await poller.is_cancelled(db, "run-1") is False
    assert calls == 1

    assert await poller.is_cancelled(db, "run-1", force=True) is False
    assert calls == 2
