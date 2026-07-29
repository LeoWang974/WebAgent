from pathlib import Path

from agent_runtime.adapters.hermes_cli import HermesCliWrapper


def test_hermes_completion_signal_accepts_chinese_and_mojibake():
    report_generated = "\u62a5\u544a\u5df2\u751f\u6210\u3002\u9a8c\u8bc1\u6587\u4ef6\uff1a"
    ppt_completed = "\u73b0\u5728\u6267\u884cPPTX\u8f6c\u6362\u5b8c\u6210"
    report_completed = "\u62a5\u544a\u5b8c\u6210\u3002\u4ea7\u51fa\u6587\u4ef6\u7ed3\u6784\uff1a"

    assert HermesCliWrapper._is_completion_signal(report_generated)
    assert HermesCliWrapper._is_completion_signal(ppt_completed)
    assert HermesCliWrapper._is_completion_signal(report_completed)
    assert HermesCliWrapper._is_completion_signal("Duration:       18m 1s")


def test_hermes_box_parser_accepts_mojibake_box_prefixes():
    wrapper = HermesCliWrapper()
    mojibake_box_line = "\u923a\uE75B\u6522 \u9200?Hermes \u9239\u20ac"
    mojibake_content_line = "\u9239?\u93b6\u30e5\u619bol\u57b6"
    mojibake_content = "\u93b6\u30e5\u619bol\u57b6"

    assert wrapper._is_box_line(mojibake_box_line)
    assert wrapper._strip_box_edges(mojibake_content_line) == mojibake_content


def test_hermes_stream_decoder_accepts_gb18030_chunks():
    content = "\u62a5\u544a\u5df2\u751f\u6210\uff0c\u4fdd\u5b58\u5728\uff1a"

    decoded = HermesCliWrapper._decode_stream_chunk(content.encode("gb18030"))

    assert content in decoded
    assert HermesCliWrapper._is_completion_signal(decoded)


def test_hermes_summarizes_long_box_to_visible_stage():
    content = "\n".join(
        [
            "\u62a5\u544a\u5df2\u751f\u6210\uff0c\u4fdd\u5b58\u5728\uff1a",
            "/home/demo/.hermes/reports/topic/report.md",
            "---",
            "\u6838\u5fc3\u53d1\u73b0",
            "\u7b2c\u4e00\u6761",
            "\u7b2c\u4e8c\u6761",
        ]
    )

    summarized = HermesCliWrapper._summarize_box_text(content)

    assert summarized is not None
    assert "\u62a5\u544a\u5df2\u751f\u6210" in summarized
    assert "report.md" in summarized
    assert len(summarized.splitlines()) <= 4


def test_hermes_stream_event_payload_contains_protocol_fields(tmp_path: Path):
    wrapper = HermesCliWrapper()
    wrapper._remember_artifact_paths("/mnt/c/Users/demo/report.md")

    event = wrapper._build_stream_event(
        content="\u62a5\u544a\u5df2\u751f\u6210\u3002\u9a8c\u8bc1\u6587\u4ef6\uff1a",
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


def test_hermes_extracts_report_path_from_generated_message():
    wrapper = HermesCliWrapper()

    wrapper._remember_artifact_paths(
        "\U0001f4c4 /home/demo/.hermes/reports/topic/topic-report.md"
    )

    assert wrapper.last_artifact_paths == ["/home/demo/.hermes/reports/topic/topic-report.md"]
    assert wrapper.last_artifacts[0]["artifact_type"] == "markdown_report"


def test_hermes_stream_event_classification():
    assert (
        HermesCliWrapper._classify_stream_event_type(
            "\u62a5\u544a\u5df2\u751f\u6210\u3002\u9a8c\u8bc1\u6587\u4ef6\uff1a",
            completion_detected=True,
        )
        == "completed"
    )
    assert (
        HermesCliWrapper._classify_stream_event_type(
            "\u751f\u6210\u6587\u4ef6 /mnt/c/Users/demo/report.md",
            completion_detected=False,
            artifact_found=True,
        )
        == "artifact_found"
    )
    assert (
        HermesCliWrapper._classify_stream_event_type(
            "read evidence.json and call terminal",
            completion_detected=False,
        )
        == "tool_call"
    )
    assert (
        HermesCliWrapper._classify_stream_event_type(
            "\u8fdb\u5165\u62a5\u544a\u64b0\u5199\u9636\u6bb5",
            completion_detected=False,
        )
        == "stage_started"
    )


def test_hermes_summarizes_raw_tool_lines_to_user_visible_status():
    assert (
        HermesCliWrapper._summarize_raw_runtime_line(
            'curl -s "https://google.serper.dev/search" -d \'{"q":"AI support"}\''
        )
        == "正在使用 Serper 搜索资料..."
    )
    assert (
        HermesCliWrapper._summarize_raw_runtime_line(
            "python3 /skills/sn-ppt-standard/scripts/run_stage.py export --deck-dir /tmp/deck"
        )
        == "正在导出 PPTX 文件..."
    )
    assert (
        HermesCliWrapper._summarize_raw_runtime_line("write /tmp/deck/pages/page_003.html")
        == "正在生成第 3 页幻灯片..."
    )
