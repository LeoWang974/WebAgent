# File purpose: Verifies repeated Hermes stage bubbles are suppressed without hiding progress.
# Main declarations: test_protocol_stage_suppresses_exact_repeat checks exact dedupe;
# test_protocol_stage_keeps_distinct_updates_in_same_category checks useful updates remain visible.

from app.services.stage_bubble_filter import (
    normalize_runtime_update,
    runtime_stage_key,
    should_suppress_stage_bubble,
)


def test_protocol_stage_suppresses_exact_repeat():
    content = "正在写入中间文件..."
    suppress, _ = should_suppress_stage_bubble(
        content,
        {"protocol": "hermes.stream.v1", "hermesEventType": "tool_call"},
        {},
        None,
        normalize_runtime_update(content),
    )

    assert suppress is True


def test_protocol_stage_keeps_distinct_updates_in_same_category():
    counts: dict[str, int] = {}
    first = "Writing report introduction."
    suppress, key = should_suppress_stage_bubble(
        "Writing report conclusion.",
        {"protocol": "hermes.stream.v1", "hermesEventType": "stage_started"},
        counts,
        "write",
        normalize_runtime_update(first),
    )

    assert key == "write"
    assert suppress is False


def test_chinese_runtime_updates_use_stable_stage_categories():
    assert runtime_stage_key("正在使用 Serper 搜索行业数据", {}) == "search"
    assert runtime_stage_key("正在抓取网页并下载资料", {}) == "fetch"
    assert runtime_stage_key("正在撰写 Markdown 报告", {}) == "write"
    assert runtime_stage_key("正在验证报告引用", {}) == "verify"
    assert runtime_stage_key("正在导出 PPTX", {}) == "export"


def test_chinese_low_value_runtime_update_is_suppressed():
    suppress, key = should_suppress_stage_bubble(
        "正在读取相关文件...",
        {},
        {},
        None,
    )

    assert key == "message:正在读取相关文件..."
    assert suppress is True
