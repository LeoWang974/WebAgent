# File purpose: Verifies repeated Hermes stage bubbles are suppressed without hiding progress.
# Main declarations: test_protocol_stage_suppresses_exact_repeat checks exact dedupe;
# test_protocol_stage_keeps_distinct_updates_in_same_category checks useful updates remain visible.

from app.services.stage_bubble_filter import (
    normalize_runtime_update,
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
