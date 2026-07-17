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

    assert event.event_type == "completion_signal"
    assert payload["protocol"] == "hermes.stream.v1"
    assert payload["completionDetected"] is True
    assert payload["artifact_paths"] == [r"C:\Users\demo\report.md"]
    assert payload["artifacts"][0]["run_id"] == "run_123"
    assert payload["artifacts"][0]["artifact_type"] == "markdown_report"
    assert payload["rawLogPath"].endswith("hermes-raw.log")
