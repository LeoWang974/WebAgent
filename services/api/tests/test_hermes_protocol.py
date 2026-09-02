# File purpose: Verifies test hermes protocol behavior and its regression contracts.
# Main declarations: test_hermes_recovers_latest_assistant_message_from_session verifies hermes
# recovers latest assistant message from session;
# test_hermes_session_recovery_ignores_sessions_from_before_run verifies hermes session recovery
# ignores sessions from before run; test_hermes_completion_signal_requires_explicit_terminal_wording
# verifies intermediate report wording does not stop a Hermes run prematurely;
# test_hermes_box_parser_accepts_mojibake_box_prefixes verifies hermes box parser accepts mojibake
# box prefixes; test_hermes_summarizes_long_box_to_visible_stage verifies hermes summarizes long
# box to visible stage; test_hermes_stream_event_payload_contains_protocol_fields verifies hermes
# stream event payload contains protocol fields;
# test_hermes_extracts_report_path_from_generated_message verifies hermes extracts report path
# from generated message; test_hermes_resolves_relative_artifacts_from_final_output verifies
# hermes resolves relative artifacts from final output;
# test_hermes_final_discovery_scans_only_run_directories verifies hermes final discovery scans
# only run directories; test_hermes_emits_artifact_found_after_final_output_discovery verifies
# hermes emits artifact found after final output discovery;
# test_hermes_session_recovery_does_not_duplicate_visible_completion verifies hermes session
# recovery does not duplicate visible completion; test_hermes_stream_event_classification verifies
# hermes stream event classification; test_hermes_summarizes_raw_tool_lines_to_user_visible_status
# verifies hermes summarizes raw tool lines to user visible status.

import asyncio
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from app.integrations.hermes import HermesCliWrapper


def test_hermes_ignores_unknown_artifact_suffix_instead_of_recording_invalid_type():
    wrapper = HermesCliWrapper()

    assert wrapper._artifact_type_from_path("/tmp/output.bin") is None
    assert wrapper._remember_artifact_path("/tmp/output.bin") is False
    assert wrapper.last_artifacts == []


def test_hermes_confirmed_box_accepts_exact_ascii_reply_but_raw_line_does_not():
    wrapper = HermesCliWrapper()

    assert wrapper._should_emit_box("QA-A-FINAL-SHORT-OK") is False
    assert (
        wrapper._should_emit_box(
            "QA-A-FINAL-SHORT-OK",
            confirmed_hermes_box=True,
        )
        is True
    )
    assert (
        wrapper._should_emit_box(
            "browser: browser_navigate",
            confirmed_hermes_box=True,
        )
        is False
    )


def test_hermes_recovers_latest_assistant_message_from_session(tmp_path: Path):
    hermes_home = tmp_path / "hermes-home"
    sessions_dir = hermes_home / "sessions"
    sessions_dir.mkdir(parents=True)
    started_at = datetime.now()
    (sessions_dir / "session_test.json").write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "Reply exactly"},
                    {"role": "assistant", "content": "EN_SHORT_OK"},
                ]
            }
        ),
        encoding="utf-8",
    )
    wrapper = HermesCliWrapper(hermes_home=str(hermes_home))

    assert (
        wrapper._recover_latest_session_assistant_content(started_at=started_at)
        == "EN_SHORT_OK"
    )


def test_hermes_session_recovery_ignores_sessions_from_before_run(tmp_path: Path):
    hermes_home = tmp_path / "hermes-home"
    sessions_dir = hermes_home / "sessions"
    sessions_dir.mkdir(parents=True)
    stale_session = sessions_dir / "session_stale.json"
    stale_session.write_text(
        json.dumps({"messages": [{"role": "assistant", "content": "STALE"}]}),
        encoding="utf-8",
    )
    stale_timestamp = datetime.now().timestamp() - 60
    stale_session.touch()
    os.utime(stale_session, (stale_timestamp, stale_timestamp))
    wrapper = HermesCliWrapper(hermes_home=str(hermes_home))

    assert wrapper._recover_latest_session_assistant_content(
        started_at=datetime.now()
    ) is None


def test_hermes_session_updates_only_return_messages_appended_after_baseline(
    tmp_path: Path,
):
    hermes_home = tmp_path / "hermes-home"
    sessions_dir = hermes_home / "sessions"
    sessions_dir.mkdir(parents=True)
    session_path = sessions_dir / "session_resumed.json"
    session_path.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "role": "assistant",
                        "content": "Old report: /tmp/old-report.md",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    wrapper = HermesCliWrapper(hermes_home=str(hermes_home))
    cursors = wrapper._session_message_counts()
    session_path.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "role": "assistant",
                        "content": "Old report: /tmp/old-report.md",
                    },
                    {
                        "role": "assistant",
                        "content": "Writing the final HTML report.",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "write_file",
                                    "arguments": '{"path":"/tmp/new-report.html"}',
                                }
                            }
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    updates, paths = wrapper._recover_session_updates(
        started_at=datetime.now(),
        message_cursors=cursors,
    )

    assert updates == ["Writing the final HTML report."]
    assert paths == [wrapper._normalize_artifact_path("/tmp/new-report.html")]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/tmp/report.md", True),
        ("/tmp/topic.html", True),
        ("/tmp/topic.pptx", True),
        ("/tmp/request.md", False),
        ("/tmp/sub_reports/d1.md", False),
        ("/tmp/pages/page_001.html", False),
        ("/tmp/plan.json", False),
    ],
)
def test_hermes_primary_completion_artifact_filter(path: str, expected: bool):
    assert HermesCliWrapper._is_primary_completion_artifact(Path(path)) is expected


def test_hermes_terminal_output_does_not_attach_stale_or_missing_artifacts(
    tmp_path: Path,
):
    stale_report = tmp_path / "stale-report.md"
    stale_report.write_text("old", encoding="utf-8")
    stale_timestamp = datetime.now().timestamp() - 60
    os.utime(stale_report, (stale_timestamp, stale_timestamp))
    wrapper = HermesCliWrapper()
    wrapper.stream_started_at = datetime.now()

    assert wrapper._remember_artifact_path(str(stale_report)) is False
    assert wrapper._remember_artifact_path(str(tmp_path / "missing.md")) is False
    assert wrapper.last_artifact_paths == []

    fresh_report = tmp_path / "fresh-report.md"
    fresh_report.write_text("new", encoding="utf-8")
    assert wrapper._remember_artifact_path(str(fresh_report)) is True


def test_hermes_completion_signal_requires_explicit_terminal_wording():
    final_report_generated = (
        "\u6700\u7ec8\u62a5\u544a\u5df2\u751f\u6210\u3002\u9a8c\u8bc1\u6587\u4ef6\uff1a"
    )
    ppt_completed = "\u73b0\u5728\u6267\u884cPPTX\u8f6c\u6362\u5b8c\u6210"
    intermediate_reports_completed = (
        "\u6240\u6709\u5b50\u62a5\u544a\u5b8c\u6210\uff0c\u5f00\u59cb\u7efc\u5408\u9636\u6bb5\u3002"
    )
    generic_report_generated = "\u62a5\u544a\u5df2\u751f\u6210\u3002\u9a8c\u8bc1\u6587\u4ef6\uff1a"
    generic_task_completed = (
        "\u5b50\u4efb\u52a1\u5df2\u5b8c\u6210\uff0c\u7ee7\u7eed\u5904\u7406\u3002"
    )

    assert HermesCliWrapper._is_completion_signal(final_report_generated)
    assert HermesCliWrapper._is_completion_signal(ppt_completed)
    assert not HermesCliWrapper._is_completion_signal(intermediate_reports_completed)
    assert not HermesCliWrapper._is_completion_signal(generic_report_generated)
    assert not HermesCliWrapper._is_completion_signal(generic_task_completed)
    assert not HermesCliWrapper._is_completion_signal("Duration:       18m 1s")


def test_hermes_terminal_provider_failure_is_detected_even_when_artifacts_exist():
    wrapper = HermesCliWrapper()

    failure = wrapper._terminal_provider_failure(
        "API call failed after 3 attempts: HTTP 401 invalid token"
    )

    assert failure is not None
    assert "invalid token" in failure.lower()


@pytest.mark.parametrize(
    "message",
    [
        "The `.pptx` file has been generated and verified.",
        "The HTML file has been generated and verified.",
        "The Markdown report has been generated and verified.",
    ],
)
def test_hermes_completion_signal_accepts_verified_english_artifacts(message: str):
    assert HermesCliWrapper._is_completion_signal(message)


def test_hermes_box_parser_accepts_mojibake_box_prefixes():
    wrapper = HermesCliWrapper()
    mojibake_box_line = "\u923a\uE75B\u6522 \u9200?Hermes \u9239\u20ac"
    mojibake_content_line = "\u9239?\u93b6\u30e5\u619bol\u57b6"
    mojibake_content = "\u93b6\u30e5\u619bol\u57b6"

    assert wrapper._is_box_line(mojibake_box_line)
    assert wrapper._strip_box_edges(mojibake_content_line) == mojibake_content


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


def test_hermes_resolves_relative_artifacts_from_final_output(tmp_path: Path):
    wrapper = HermesCliWrapper()
    pptx_path = tmp_path / "2026 AI assistant trends.pptx"
    html_path = tmp_path / "deck-preview.html"
    with zipfile.ZipFile(pptx_path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
    html_path.write_text("<html></html>", encoding="utf-8")

    wrapper._remember_final_output_artifact_paths(
        (
            "PPTX（主交付物）：2026 AI assistant trends.pptx\n"
            "HTML preview: deck-preview.html"
        ),
        working_dir=str(tmp_path),
        artifacts_dir=None,
    )

    assert str(pptx_path.resolve()) in wrapper.last_artifact_paths
    assert str(html_path.resolve()) in wrapper.last_artifact_paths
    artifact_types = {item["artifact_type"] for item in wrapper.last_artifacts}
    assert {"ppt_deck", "html_page"}.issubset(artifact_types)


def test_hermes_resolves_reports_path_without_ingesting_repository_docs(
    tmp_path: Path,
):
    wrapper = HermesCliWrapper()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    report_path = reports_dir / "generated.md"
    readme_path = tmp_path / "README.md"
    report_path.write_text("# Generated report", encoding="utf-8")
    readme_path.write_text("# Repository documentation", encoding="utf-8")

    wrapper._remember_final_output_artifact_paths(
        "报告已保存到 ./reports/generated.md，相关命令见 README.md。",
        working_dir=str(tmp_path),
        artifacts_dir=None,
    )

    assert wrapper.last_artifact_paths == [str(report_path.resolve())]


def test_hermes_final_discovery_scans_only_run_directories(tmp_path: Path):
    wrapper = HermesCliWrapper()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    pptx_path = run_dir / "final.pptx"
    pptx_path.write_bytes(b"pptx")

    wrapper._discover_run_directory_artifacts(
        working_dir=str(run_dir),
        artifacts_dir=None,
        started_at=datetime.fromtimestamp(pptx_path.stat().st_mtime),
    )

    assert wrapper.last_artifact_paths == [str(pptx_path.resolve())]


@pytest.mark.asyncio
async def test_hermes_emits_artifact_found_after_final_output_discovery(
    tmp_path: Path,
    monkeypatch,
):
    wrapper = HermesCliWrapper()
    pptx_path = tmp_path / "final-deck.pptx"
    with zipfile.ZipFile(pptx_path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")

    stdout = asyncio.StreamReader()
    stdout.feed_data(b"PPTX: final-deck.pptx\n")
    stdout.feed_eof()
    stderr = asyncio.StreamReader()
    stderr.feed_eof()

    class FakeProcess:
        pid = 12345
        returncode = 0

        def __init__(self):
            self.stdout = stdout
            self.stderr = stderr

        async def wait(self):
            return self.returncode

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(wrapper, "_build_chat_exec_args", lambda *args, **kwargs: ["hermes"])
    monkeypatch.setattr(
        wrapper,
        "_raw_log_path",
        lambda run_id=None: tmp_path / "hermes-raw.log",
    )

    events = [
        event
        async for event in wrapper.ask_stream_events(
            "create a deck",
            conversation_id="conversation-1",
            run_id="run-1",
            working_dir=str(tmp_path),
            artifacts_dir=str(tmp_path / "artifacts"),
        )
    ]

    artifact_event = next(event for event in events if event.event_type == "artifact_found")
    manifest_event = next(
        event for event in events if event.event_type == "artifact_manifest_finalized"
    )
    assert artifact_event.artifact_paths == [str(pptx_path.resolve())]
    assert artifact_event.payload["finalDiscovery"] is True
    assert wrapper._env["WEBAGENT_CONVERSATION_ID"] == "conversation-1"
    assert wrapper._env["WEBAGENT_RUN_ID"] == "run-1"
    assert wrapper._env["WEBAGENT_RUNTIME_POLICY"] == "managed-artifacts-v3"
    assert wrapper._env["WEBAGENT_OUTPUT_DIR"] == wrapper._env["WEBAGENT_ARTIFACTS_DIR"]
    assert wrapper.last_diagnostics["runtime_instruction_injected"] is False
    manifest_path = tmp_path / "artifacts" / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "webagent.artifacts.v3"
    assert manifest["status"] == "finalized"
    assert manifest["run_id"] == "run-1"
    assert manifest["artifacts"][0]["sha256"]
    assert artifact_event.payload["artifactManifestSchema"] == "webagent.artifacts.v3"
    assert manifest_event.payload["artifactManifestFinalized"] is True
    assert manifest_event.payload["artifactManifestEntryCount"] == 1


@pytest.mark.asyncio
async def test_hermes_session_recovery_does_not_duplicate_visible_completion(
    tmp_path: Path,
    monkeypatch,
):
    hermes_home = tmp_path / "hermes-home"
    sessions_dir = hermes_home / "sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "session_test.json").write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "create report"},
                    {"role": "assistant", "content": "Report completed with details."},
                ]
            }
        ),
        encoding="utf-8",
    )
    wrapper = HermesCliWrapper(hermes_home=str(hermes_home))
    stdout = asyncio.StreamReader()
    stdout.feed_data(
        "╭─ ⚕ Hermes ─╮\n│ Report completed.\n╰────────────╯\n".encode()
    )
    stdout.feed_eof()
    stderr = asyncio.StreamReader()
    stderr.feed_eof()

    class FakeProcess:
        pid = 12346
        returncode = 0

        def __init__(self):
            self.stdout = stdout
            self.stderr = stderr

        async def wait(self):
            return self.returncode

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(wrapper, "_build_chat_exec_args", lambda *args, **kwargs: ["hermes"])
    monkeypatch.setattr(
        wrapper,
        "_raw_log_path",
        lambda run_id=None: tmp_path / "hermes-raw.log",
    )

    events = [
        event
        async for event in wrapper.ask_stream_events(
            "create report",
            run_id="run-1",
            working_dir=str(tmp_path),
        )
    ]

    completed = [event for event in events if event.event_type == "completed"]
    assert len(completed) == 1
    assert completed[0].content == "Report completed with details."
    assert completed[0].payload.get("sessionRecovery") is True
    stage_events = [event for event in events if event.content == "Report completed."]
    assert len(stage_events) == 1
    assert stage_events[0].event_type == "stage_started"
    assert stage_events[0].payload.get("sessionRecovery") is None


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


@pytest.mark.parametrize(
    "message",
    [
        "API call failed after 3 retries: Connection error.",
        "API failed after 3 retries - Rate limited.",
        "Non-retryable error (HTTP 401): Unauthorized",
        "Invalid token for configured provider",
    ],
)
def test_hermes_detects_terminal_provider_failures(message: str):
    assert HermesCliWrapper._terminal_provider_failure(message) == message


def test_hermes_does_not_stop_on_transient_provider_retry():
    assert (
        HermesCliWrapper._terminal_provider_failure(
            "API call failed (attempt 1/3): APIConnectionError"
        )
        is None
    )


@pytest.mark.asyncio
async def test_hermes_stream_fails_fast_after_terminal_provider_error(
    monkeypatch, tmp_path: Path
):
    wrapper = HermesCliWrapper()
    stdout = asyncio.StreamReader()
    stdout.feed_data(b"API call failed after 3 retries: Connection error.\n")
    stdout.feed_eof()
    stderr = asyncio.StreamReader()
    stderr.feed_eof()

    class FakeProcess:
        pid = 12347
        returncode = 1

        def __init__(self):
            self.stdout = stdout
            self.stderr = stderr

        async def wait(self):
            return self.returncode

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(wrapper, "_build_chat_exec_args", lambda *args, **kwargs: ["hermes"])
    monkeypatch.setattr(
        wrapper,
        "_raw_log_path",
        lambda run_id=None: tmp_path / "hermes-raw.log",
    )

    with pytest.raises(RuntimeError, match="API call failed after 3 retries"):
        [
            event
            async for event in wrapper.ask_stream_events(
                "hello",
                working_dir=str(tmp_path),
            )
        ]

    assert wrapper.last_diagnostics["provider_failure"] == (
        "API call failed after 3 retries: Connection error."
    )
