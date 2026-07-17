import os

from agent_runtime.adapters.openclaw_adapter import OpenClawAdapter
from agent_runtime.schemas import AgentRunCreate


def test_openclaw_adapter_builds_platform_cli_args(monkeypatch):
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30)
    input_data = AgentRunCreate(
        content="hello",
        session_id="session_123",
        run_id="run_123",
    )

    args = adapter._build_local_cli_args(input_data)

    if os.name == "nt":
        assert args[:4] == ["wsl.exe", "--", "bash", "-lc"]
        assert "openclaw agent" in args[4]
    else:
        assert args[:2] == ["openclaw", "agent"]
    joined = " ".join(args)
    assert "--local" in joined
    assert "--agent" in joined
    assert "main" in joined
    assert "--message" in joined
    assert "hello" in joined
    assert "--session-id" in joined
    assert "session_123" in joined


def test_openclaw_adapter_extracts_json_output():
    output = OpenClawAdapter._extract_output(
        '{"reply":"OpenClaw connected"}',
        "",
    )

    assert output == "OpenClaw connected"


def test_openclaw_adapter_extracts_payload_text_from_stderr_json():
    output = OpenClawAdapter._extract_output(
        "",
        '{"payloads":[{"text":"connected ✅","mediaUrl":null}],"meta":{"durationMs":10}}',
    )

    assert output == "connected ✅"


def test_openclaw_adapter_cleans_text_output_and_skips_warnings():
    output = OpenClawAdapter._extract_output(
        "OpenClaw\n\x1b[36m[skills]\x1b[39m Skipping path\n",
        "",
    )

    assert output == "OpenClaw"


def test_openclaw_adapter_extracts_artifact_refs():
    adapter = OpenClawAdapter()

    adapter._remember_artifact_paths(
        "Generated /mnt/c/Users/demo/report.md and C:\\Users\\demo\\deck.pptx"
    )

    artifacts = adapter.get_last_artifacts()
    assert adapter.get_last_artifact_paths() == [
        "/mnt/c/Users/demo/report.md",
        "C:\\Users\\demo\\deck.pptx",
    ]
    assert artifacts[0].artifact_type == "markdown_report"
    assert artifacts[1].artifact_type == "ppt_deck"


def test_openclaw_adapter_skips_bootstrap_artifact_refs():
    adapter = OpenClawAdapter()

    adapter._remember_artifact_paths(
        "Loaded /home/demo/.openclaw/workspace/AGENTS.md and generated "
        "/home/demo/.openclaw/workspace/report.md"
    )

    assert adapter.get_last_artifact_paths() == ["/home/demo/.openclaw/workspace/report.md"]
