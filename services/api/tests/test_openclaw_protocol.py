

from agent_runtime.adapters.openclaw_adapter import OpenClawAdapter
from agent_runtime.adapters.openclaw_utils import (
    OPENCLAW_EVENT_PROTOCOL,
    extract_output,
    extract_protocol_events,
)


def test_openclaw_adapter_extracts_json_output():
    output = extract_output(
        '{"reply":"OpenClaw connected"}',
        "",
    )

    assert output == "OpenClaw connected"


def test_openclaw_adapter_extracts_payload_text_from_stderr_json():
    output = extract_output(
        "",
        '{"payloads":[{"text":"connected","mediaUrl":null}],"meta":{"durationMs":10}}',
    )

    assert output == "connected"


def test_openclaw_adapter_reads_json_from_stderr_bytes():
    payload = OpenClawAdapter._first_json_like_text(
        b"",
        b'{"tasks":[{"status":"succeeded"}]}',
    )

    assert payload == '{"tasks":[{"status":"succeeded"}]}'


def test_openclaw_adapter_extracts_standard_protocol_events():
    payload = {
        "taskId": "task-main",
        "status": "running",
        "events": [
            {
                "protocol": OPENCLAW_EVENT_PROTOCOL,
                "event_type": "tool_call",
                "label": "Searching convenience store fresh food cases",
                "progress": 32,
            },
            {
                "protocol": OPENCLAW_EVENT_PROTOCOL,
                "event_type": "artifact_found",
                "label": "Report generated",
                "artifact_paths": [
                    "/home/demo/.openclaw/workspace/reports/topic/report.md"
                ],
                "artifact_type": "markdown_report",
                "source_dir": "/home/demo/.openclaw/workspace/reports/topic",
                "title": "Convenience store fresh food report",
                "progress": 90,
            },
        ],
    }

    events = extract_protocol_events(payload)

    assert [event["event_type"] for event in events] == [
        "tool_call",
        "artifact_found",
    ]
    assert events[0]["label"] == "Searching convenience store fresh food cases"
    assert events[0]["source"]["taskId"] == "task-main"
    artifacts = events[1]["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0].path.endswith("/report.md")
    assert artifacts[0].artifact_type == "markdown_report"


def test_openclaw_adapter_extracts_gateway_result_payload_text():
    output = extract_output(
        '{"runId":"run_1","status":"ok","result":{"payloads":[{"text":"gateway connected"}]}}',
        "",
    )

    assert output == "gateway connected"


def test_openclaw_adapter_cleans_text_output_and_skips_warnings():
    output = extract_output(
        "OpenClaw\n\x1b[36m[skills]\x1b[39m Skipping path\n",
        "",
    )

    assert output == "OpenClaw"
