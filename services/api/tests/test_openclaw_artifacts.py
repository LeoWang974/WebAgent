from pathlib import Path

from agent_runtime.adapters.openclaw_adapter import OpenClawAdapter
from agent_runtime.adapters.openclaw_utils import (
    artifact_to_payload,
    extract_structured_artifact_paths,
    extract_structured_artifacts,
)
from agent_runtime.schemas import AgentRunCreate


def test_openclaw_adapter_ignores_auxiliary_markdown_as_primary_artifacts():
    assert not OpenClawAdapter._is_primary_output_artifact(
        "/home/demo/deep-research-reports/topic/request.md"
    )
    assert not OpenClawAdapter._is_primary_output_artifact(
        "/home/demo/deep-research-reports/topic/synthesis.md"
    )
    assert not OpenClawAdapter._is_primary_output_artifact(
        "/home/demo/deep-research-reports/topic/sub_reports/d1.md"
    )
    assert OpenClawAdapter._is_primary_output_artifact(
        "/home/demo/deep-research-reports/topic/report.md"
    )


def test_openclaw_adapter_extracts_report_dir_search_needles():
    needles = OpenClawAdapter._report_dir_search_needles(
        "[User request]\ncity night economy opportunity report\n[Context]"
    )

    assert "city night economy opportunity report" in needles


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
    paths = extract_structured_artifact_paths(
        "",
        '{"payloads":[{"text":"done","mediaUrl":"/mnt/c/Users/demo/image.png"}],'
        '"artifact_paths":["/mnt/c/Users/demo/report.md"]}',
    )

    assert paths == ["/mnt/c/Users/demo/report.md", "/mnt/c/Users/demo/image.png"]


def test_openclaw_adapter_extracts_structured_artifact_refs():
    refs = extract_structured_artifacts(
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
    payload = artifact_to_payload(
        extract_structured_artifacts(
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


def test_openclaw_adapter_primary_output_excludes_debug_json():
    assert not OpenClawAdapter._is_primary_output_artifact("/home/demo/briefing.json")
    assert not OpenClawAdapter._is_primary_output_artifact(
        "/home/demo/deep-research-reports/topic/sub_reports/d3-subreport.md"
    )
    assert OpenClawAdapter._is_primary_output_artifact("/home/demo/report.md")


def test_openclaw_adapter_ppt_primary_output_ignores_source_markdown():
    adapter = OpenClawAdapter()
    adapter._remember_artifact_paths(
        "Use C:\\Users\\demo\\Downloads\\report.md and generated "
        "C:\\Users\\demo\\Downloads\\deck.pptx"
    )

    assert adapter._primary_output_artifact_paths("ppt_generation") == [
        "C:\\Users\\demo\\Downloads\\deck.pptx"
    ]


def test_openclaw_adapter_ppt_primary_output_does_not_accept_html_as_ppt():
    adapter = OpenClawAdapter()
    adapter._remember_artifact_paths(
        "Generated /home/demo/report.html and /home/demo/deck.pptx"
    )

    assert adapter._primary_output_artifact_paths("ppt_generation") == [
        "/home/demo/deck.pptx"
    ]


def test_openclaw_adapter_ppt_fallback_waits_longer_than_slow_exports():
    adapter = OpenClawAdapter(command_timeout_seconds=600)

    assert adapter._no_task_family_timeout_seconds("ppt_generation") >= 25 * 60
    assert adapter._no_artifact_timeout_seconds("ppt_generation") >= 25 * 60


def test_openclaw_adapter_html_fallback_waits_for_background_export():
    adapter = OpenClawAdapter(command_timeout_seconds=600)

    assert adapter._no_task_family_timeout_seconds("html_generation") >= 20 * 60
    assert adapter._no_artifact_timeout_seconds("html_generation") >= 20 * 60


def test_openclaw_adapter_recent_ppt_requires_prompt_match():
    input_data = AgentRunCreate(
        content="请使用《城市夜经济新机会》报告生成 PPT。",
        session_id="session_123",
        run_id="run_123",
        skill_key=None,
    )

    assert OpenClawAdapter._recent_artifact_matches_input(
        "/home/demo/.openclaw/workspace/城市夜经济新机会.pptx",
        "ppt_generation",
        input_data,
    )
    assert not OpenClawAdapter._recent_artifact_matches_input(
        "/home/demo/.openclaw/workspace/OpenClaw_同用户并发测试2.pptx",
        "ppt_generation",
        input_data,
    )


def test_openclaw_adapter_recent_ppt_without_prompt_match_is_rejected():
    input_data = AgentRunCreate(
        content="Use the generated Markdown/HTML report above and create an 8-page PPT.",
        session_id="session_123",
        run_id="run_123",
        skill_key=None,
    )

    assert not OpenClawAdapter._recent_artifact_matches_input(
        "/home/demo/.openclaw/workspace/OpenClaw_同用户并发测试2.pptx",
        "ppt_generation",
        input_data,
    )


def test_openclaw_adapter_extracts_windows_input_parent_dirs():
    dirs = OpenClawAdapter._extract_file_parent_dirs(
        "C:\\Users\\demo\\Downloads\\report-50ffa786ad.md閹躲儱鎲￠敍宀€鏁撻幋鎬璓T"
    )

    assert "/mnt/c/Users/demo/Downloads" in dirs


def test_openclaw_adapter_skips_bootstrap_artifact_refs():
    adapter = OpenClawAdapter()

    adapter._remember_artifact_paths(
        "Loaded /home/demo/.openclaw/workspace/AGENTS.md and generated "
        "/home/demo/.openclaw/workspace/report.md"
    )

    assert adapter.get_last_artifact_paths() == ["/home/demo/.openclaw/workspace/report.md"]


def test_openclaw_adapter_creates_fallback_markdown_artifact(tmp_path, monkeypatch):
    adapter = OpenClawAdapter()
    monkeypatch.setattr(
        "agent_runtime.adapters.openclaw_adapter.Path.resolve",
        lambda self: tmp_path
        / "services"
        / "agent-runtime"
        / "agent_runtime"
        / "adapters"
        / "openclaw_adapter.py",
    )
    content = "# Theme park competition\n\n" + (
        "Disney, Universal, Fantawild, and Chimelong business model analysis.\n" * 4
    )

    adapter._create_fallback_artifact_from_output(
        AgentRunCreate(
            content="Output Chinese Markdown report",
            session_id="session_123",
            run_id="run_123",
            skill_key="deep_research",
        ),
        "run_123",
        content,
    )

    artifacts = adapter.get_last_artifacts()
    assert len(artifacts) == 1
    assert artifacts[0].artifact_type == "markdown_report"
    assert artifacts[0].run_id == "run_123"
    assert Path(artifacts[0].path).read_text(encoding="utf-8") == content.strip()
