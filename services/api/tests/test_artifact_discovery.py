from datetime import datetime, timedelta
from pathlib import Path

from agent_runtime.schemas import AgentArtifactRef

from app.services import mock_store
from app.services.artifact_discovery import (
    _candidate_roots,
    _normalized_path_key,
    create_artifacts_from_paths,
    create_artifacts_from_refs,
    discover_related_artifact_paths,
)


def test_normalized_path_key_unifies_windows_and_wsl_paths():
    assert _normalized_path_key(r"C:\Users\demo\report.md") == "/mnt/c/users/demo/report.md"
    assert (
        _normalized_path_key(r"\\wsl.localhost\Ubuntu\home\demo\report.md")
        == "/home/demo/report.md"
    )
    assert _normalized_path_key("/home/demo/report.md") == "/home/demo/report.md"


def test_candidate_roots_include_hermes_deep_research_reports():
    roots = [str(root).replace("\\", "/") for root in _candidate_roots()]

    assert any("/.hermes/deep-research-reports" in root for root in roots)


def test_create_artifacts_from_paths_dedupes_by_content_hash(tmp_path: Path):
    original_artifacts = list(mock_store.artifacts)
    try:
        mock_store.artifacts.clear()
        first = tmp_path / "report.md"
        second = tmp_path / "copy.md"
        first.write_text("# Report\nsame content", encoding="utf-8")
        second.write_text("# Report\nsame content", encoding="utf-8")

        artifacts = create_artifacts_from_paths("session_1", [str(first), str(second)])

        assert len(artifacts) == 1
        assert artifacts[0].type == "markdown_report"
        assert artifacts[0].content == "# Report\nsame content"
        assert artifacts[0].metadata
        assert artifacts[0].metadata["contentHash"]
    finally:
        mock_store.artifacts[:] = original_artifacts


def test_create_artifacts_from_paths_supports_debug_json(tmp_path: Path):
    original_artifacts = list(mock_store.artifacts)
    try:
        mock_store.artifacts.clear()
        json_file = tmp_path / "briefing.json"
        json_file.write_text('{"topic":"future food","steps":2}', encoding="utf-8")

        artifacts = create_artifacts_from_paths("session_1", [str(json_file)])

        assert len(artifacts) == 1
        assert artifacts[0].type == "debug_json"
        assert artifacts[0].content == '{"topic":"future food","steps":2}'
        assert artifacts[0].metadata
        assert artifacts[0].metadata["filename"] == "briefing.json"
    finally:
        mock_store.artifacts[:] = original_artifacts


def test_create_artifacts_from_refs_preserves_openclaw_protocol_metadata(tmp_path: Path):
    original_artifacts = list(mock_store.artifacts)
    try:
        mock_store.artifacts.clear()
        report = tmp_path / "openclaw-report.md"
        report.write_text("# OpenClaw Report\n", encoding="utf-8")

        artifacts = create_artifacts_from_refs(
            "session_1",
            [
                AgentArtifactRef(
                    path=str(report),
                    artifact_type="markdown_report",
                    run_id="openclaw_run_1",
                    source_dir=str(tmp_path),
                    title="OpenClaw 标准报告",
                )
            ],
            run_id="webagent_run_1",
        )

        assert len(artifacts) == 1
        artifact = artifacts[0]
        assert artifact.type == "markdown_report"
        assert artifact.title == "OpenClaw 标准报告"
        assert artifact.content == "# OpenClaw Report\n"
        assert artifact.metadata
        assert artifact.metadata["adapterProtocol"] == "openclaw.artifact.v1"
        assert artifact.metadata["adapterRunId"] == "openclaw_run_1"
        assert artifact.metadata["adapterSourceDir"] == str(tmp_path)
        assert artifact.metadata["adapterTitle"] == "OpenClaw 标准报告"
        assert artifact.metadata["adapterType"] == "markdown_report"
    finally:
        mock_store.artifacts[:] = original_artifacts


def test_discover_related_artifact_paths_finds_html_slides_for_pptx(tmp_path: Path):
    deck = tmp_path / "deck.pptx"
    slide = tmp_path / "page_001.html"
    deck.write_bytes(b"pptx")
    slide.write_text("<html><body>slide</body></html>", encoding="utf-8")

    since = datetime.fromtimestamp(deck.stat().st_mtime) - timedelta(seconds=1)
    paths = discover_related_artifact_paths([str(deck)], since)

    normalized = {Path(path).name for path in paths}
    assert "deck.pptx" in normalized
    assert "page_001.html" in normalized
