from pathlib import Path

from agent_runtime.adapters.hermes_cli import HermesCliWrapper


def test_hermes_completion_signal_accepts_utf8_chinese():
    assert HermesCliWrapper._is_completion_signal("报告已生成。验证文件：")
    assert HermesCliWrapper._is_completion_signal("现在执行PPTX转换完成")


def test_hermes_stream_event_payload_contains_protocol_fields(tmp_path: Path):
    wrapper = HermesCliWrapper()
    wrapper._remember_artifact_paths("/mnt/c/Users/demo/report.md")

    event = wrapper._build_stream_event(
        content="报告已生成。验证文件：",
        raw_log_path=tmp_path / "hermes-raw.log",
        run_id="run_123",
        completion_detected=True,
    )
    payload = event.to_payload()

    assert event.event_type == "completed"
    assert payload["protocol"] == "hermes.stream.v1"
    assert payload["hermesEventType"] == "completed"
    assert payload["rawHermesEventType"] == "completion_signal"
    assert payload["completionDetected"] is True
    assert payload["artifact_paths"] == [r"C:\Users\demo\report.md"]
    assert payload["artifacts"][0]["run_id"] == "run_123"
    assert payload["artifacts"][0]["artifact_type"] == "markdown_report"
    assert payload["rawLogPath"].endswith("hermes-raw.log")


def test_hermes_stream_event_classification():
    assert (
        HermesCliWrapper._classify_stream_event_type(
            "报告已生成。验证文件：",
            completion_detected=True,
        )
        == "completed"
    )
    assert (
        HermesCliWrapper._classify_stream_event_type(
            "生成文件 /mnt/c/Users/demo/report.md",
            completion_detected=False,
            artifact_found=True,
        )
        == "artifact_found"
    )
    assert (
        HermesCliWrapper._classify_stream_event_type(
            "读取 evidence.json 并调用 terminal",
            completion_detected=False,
        )
        == "tool_call"
    )
    assert (
        HermesCliWrapper._classify_stream_event_type(
            "进入报告撰写阶段",
            completion_detected=False,
        )
        == "stage_started"
    )
