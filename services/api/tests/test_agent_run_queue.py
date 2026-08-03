from app.services.agent_run_queue import is_short_chat_request, queue_for_message


def test_short_chat_request_uses_priority_queue():
    assert is_short_chat_request("你好", None) is True
    queue_name, queue_reason = queue_for_message("你好", None)

    assert queue_name == "short-chat"
    assert queue_reason == "短对话优先队列"


def test_artifact_requests_stay_on_long_task_queue():
    for prompt in (
        "请输出中文 Markdown 报告",
        "基于上述报告生成 HTML 文件",
        "生成一份 12 页 PPT",
    ):
        assert is_short_chat_request(prompt, None) is False
        assert queue_for_message(prompt, None)[0] == "agent-runs"


def test_explicit_skill_stays_on_long_task_queue():
    assert is_short_chat_request("你好", "deep_research") is False
    assert queue_for_message("你好", "deep_research")[0] == "agent-runs"
