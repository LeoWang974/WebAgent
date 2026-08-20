# File purpose: Verifies agent-run queue classification and cancellation polling behavior.
# Main declarations: queue classification tests cover short, artifact, validation-token, and
# long requests; cancellation polling test verifies database-read throttling.

from types import SimpleNamespace

import pytest

from app.services import agent_run_control
from app.services.agent_run_control import AgentRunCancellationPoller
from app.services.agent_run_queue import is_short_chat_request, queue_for_message


def test_short_chat_request_uses_priority_queue():
    assert is_short_chat_request("你好") is True
    queue_name, queue_reason = queue_for_message("你好")

    assert queue_name == "short-chat"
    assert queue_reason == "短对话优先队列"


def test_artifact_requests_stay_on_long_task_queue():
    for prompt in (
        "请输出中文 Markdown 报告",
        "基于上述报告生成 HTML 文件",
        "生成一份 12 页 PPT",
    ):
        assert is_short_chat_request(prompt) is False
        assert queue_for_message(prompt)[0] == "agent-runs"


def test_short_question_about_previous_artifact_uses_priority_queue():
    assert is_short_chat_request("请只回答：我上一轮要求生成几页 PPT？") is True
    assert is_short_chat_request("How many slides did I ask for last turn?") is True


def test_artifact_word_inside_validation_token_stays_on_short_queue():
    prompt = "Reply with QA-B-AFTER-PPT-OK only."

    assert is_short_chat_request(prompt) is True
    assert queue_for_message(prompt)[0] == "short-chat"


def test_long_plain_request_stays_on_long_task_queue():
    prompt = "请详细分析这个主题，并给出完整论证、风险、案例和实施建议。" * 3
    assert is_short_chat_request(prompt) is False
    assert queue_for_message(prompt)[0] == "agent-runs"


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
