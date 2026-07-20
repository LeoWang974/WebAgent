import os

from agent_runtime.adapters.openclaw_adapter import OpenClawAdapter
from agent_runtime.schemas import AgentRunCreate


def test_openclaw_adapter_builds_gateway_cli_args():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30)
    input_data = AgentRunCreate(
        content="hello",
        session_id="session_123",
        run_id="run_123",
    )

    args = adapter._build_agent_cli_args(input_data)

    if os.name == "nt":
        assert args[:4] == ["wsl.exe", "--", "bash", "-lc"]
        assert "openclaw agent" in args[4]
    else:
        assert args[:2] == ["openclaw", "agent"]
    joined = " ".join(args)
    assert "--local" not in joined
    assert "--agent" in joined
    assert "main" in joined
    assert "--message" in joined
    assert "hello" in joined
    assert "--session-id" in joined
    assert "session_123" in joined
    if os.name == "nt":
        assert "~/.hermes/.env" in joined
        assert "~/.openclaw/.env" in joined


def test_openclaw_adapter_can_build_local_cli_args():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30, mode="local_cli")

    args = adapter._build_agent_cli_args(
        AgentRunCreate(content="hello", session_id="session_123", run_id="run_123")
    )

    assert "--local" in " ".join(args)


def test_openclaw_adapter_extracts_json_output():
    output = OpenClawAdapter._extract_output(
        '{"reply":"OpenClaw connected"}',
        "",
    )

    assert output == "OpenClaw connected"


def test_openclaw_adapter_extracts_payload_text_from_stderr_json():
    output = OpenClawAdapter._extract_output(
        "",
        '{"payloads":[{"text":"connected","mediaUrl":null}],"meta":{"durationMs":10}}',
    )

    assert output == "connected"


def test_openclaw_adapter_extracts_gateway_result_payload_text():
    output = OpenClawAdapter._extract_output(
        '{"runId":"run_1","status":"ok","result":{"payloads":[{"text":"gateway connected"}]}}',
        "",
    )

    assert output == "gateway connected"


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
    assert artifacts[0].source_dir
    assert artifacts[0].title == "report"
    assert artifacts[1].artifact_type == "ppt_deck"


def test_openclaw_adapter_extracts_structured_artifact_paths():
    paths = OpenClawAdapter._extract_structured_artifact_paths(
        "",
        '{"payloads":[{"text":"done","mediaUrl":"/mnt/c/Users/demo/image.png"}],'
        '"artifact_paths":["/mnt/c/Users/demo/report.md"]}',
    )

    assert paths == ["/mnt/c/Users/demo/report.md", "/mnt/c/Users/demo/image.png"]


def test_openclaw_adapter_extracts_structured_artifact_refs():
    refs = OpenClawAdapter._extract_structured_artifacts(
        "",
        (
            '{"run_id":"openclaw_run_1","source_dir":"/mnt/c/Users/demo/output",'
            '"artifacts":[{"artifact_paths":["/mnt/c/Users/demo/output/report.md"],'
            '"artifact_type":"markdown_report","title":"Market Report"}]}'
        ),
    )

    assert len(refs) == 1
    assert refs[0].path == "/mnt/c/Users/demo/output/report.md"
    assert refs[0].artifact_type == "markdown_report"
    assert refs[0].source_dir == "/mnt/c/Users/demo/output"
    assert refs[0].run_id == "openclaw_run_1"
    assert refs[0].title == "Market Report"


def test_openclaw_adapter_artifact_payload_uses_standard_protocol_fields():
    payload = OpenClawAdapter._artifact_to_payload(
        OpenClawAdapter._extract_structured_artifacts(
            "",
            (
                '{"artifact_path":"/mnt/c/Users/demo/output/chart.png",'
                '"artifact_type":"image_result","source_dir":"/mnt/c/Users/demo/output",'
                '"run_id":"openclaw_run_2","title":"Chart"}'
            ),
        )[0]
    )

    assert payload == {
        "artifact_paths": ["/mnt/c/Users/demo/output/chart.png"],
        "artifact_path": "/mnt/c/Users/demo/output/chart.png",
        "artifact_type": "image_result",
        "run_id": "openclaw_run_2",
        "source_dir": "/mnt/c/Users/demo/output",
        "title": "Chart",
    }


def test_openclaw_adapter_skips_bootstrap_artifact_refs():
    adapter = OpenClawAdapter()

    adapter._remember_artifact_paths(
        "Loaded /home/demo/.openclaw/workspace/AGENTS.md and generated "
        "/home/demo/.openclaw/workspace/report.md"
    )

    assert adapter.get_last_artifact_paths() == ["/home/demo/.openclaw/workspace/report.md"]
