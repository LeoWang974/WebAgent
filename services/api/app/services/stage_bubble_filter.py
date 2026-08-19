# File purpose: Implements the stage bubble filter backend service workflow.
# Main declarations: normalize_runtime_update normalizes runtime update; runtime_stage_key handles
# runtime stage key; is_low_value_runtime_update checks low value runtime update;
# should_suppress_stage_bubble decides suppress stage bubble.

import re


def normalize_runtime_update(content: str) -> str:
    return re.sub(r"\s+", " ", content).strip().lower()


def runtime_stage_key(content: str, event_payload: dict) -> str:
    if event_payload.get("rawActivityHeartbeat"):
        return "heartbeat"
    normalized = normalize_runtime_update(content)
    stage_patterns = [
        ("complete", ("complete", "completed", "succeeded", "done", "generated")),
        ("export", ("export", "convert", "pptx", "html", "deck")),
        ("verify", ("validate", "verify", "check", "quality")),
        ("write", ("write", "writing", "report", "markdown", "draft")),
        ("plan", ("plan", "outline", "briefing", "blueprint")),
        ("fetch", ("fetch", "crawl", "browser", "scrape", "download")),
        ("search", ("search", "serper", "query")),
        ("file_io", ("read_file", "write_file", "reading file", "writing file")),
    ]
    for key, markers in stage_patterns:
        if any(marker in normalized for marker in markers):
            return key
    return f"message:{normalized[:96]}"


def is_low_value_runtime_update(content: str, event_payload: dict) -> bool:
    del event_payload
    normalized = normalize_runtime_update(content)
    low_value_messages = {
        "hermes is still running; raw output is being received.",
        "reading related files...",
        "writing intermediate files...",
        "finding related files and artifacts...",
        "preparing task configuration files...",
    }
    return normalized in low_value_messages


def should_suppress_stage_bubble(
    content: str,
    event_payload: dict,
    stage_counts: dict[str, int],
    last_stage_key: str | None,
) -> tuple[bool, str]:
    stage_key = runtime_stage_key(content, event_payload)
    if is_low_value_runtime_update(content, event_payload):
        return True, stage_key
    protocol = str(event_payload.get("protocol") or "")
    event_type = str(event_payload.get("hermesEventType") or "")
    if protocol and event_type in {
        "stage_started",
        "tool_call",
        "artifact_found",
        "completed",
    }:
        stage_counts[stage_key] = stage_counts.get(stage_key, 0) + 1
        return False, stage_key
    if stage_key == last_stage_key and stage_key not in {"complete", "export"}:
        return True, stage_key
    count = stage_counts.get(stage_key, 0)
    stage_counts[stage_key] = count + 1
    repeat_limits = {
        "search": 2,
        "fetch": 2,
        "plan": 2,
        "write": 3,
        "verify": 2,
        "export": 3,
        "file_io": 0,
    }
    limit = repeat_limits.get(stage_key)
    return limit is not None and count >= limit, stage_key
