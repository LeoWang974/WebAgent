from datetime import datetime, timedelta
from pathlib import Path

from agent_runtime.schemas import AgentArtifactRef
from app.services.artifact_discovery import (
    _candidate_roots,
    _normalized_path_key,
    _repo_root,
    create_artifacts_from_paths,
    create_artifacts_from_refs,
    discover_related_artifact_paths,
    extract_artifact_path_strings,
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
    repo_root = str(_repo_root()).replace("\\", "/")

    assert any("/.hermes/deep-research-reports" in root for root in roots)
    assert f"{repo_root}/deep-research-reports" in roots


def test_create_artifacts_from_paths_dedupes_by_content_hash(tmp_path: Path):
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


def test_create_artifacts_from_paths_supports_debug_json(tmp_path: Path):
    json_file = tmp_path / "briefing.json"
    json_file.write_text('{"topic":"future food","steps":2}', encoding="utf-8")

    artifacts = create_artifacts_from_paths("session_1", [str(json_file)])

    assert len(artifacts) == 1
    assert artifacts[0].type == "debug_json"
    assert artifacts[0].content == '{"topic":"future food","steps":2}'
    assert artifacts[0].metadata
    assert artifacts[0].metadata["filename"] == "briefing.json"


def test_create_artifacts_from_paths_ignores_runtime_temp_json():
    runtime_file = _repo_root() / "runtime" / "openclaw_smoke_snapshot.json"
    try:
        runtime_file.parent.mkdir(parents=True, exist_ok=True)
        runtime_file.write_text('{"status":"running"}', encoding="utf-8")

        artifacts = create_artifacts_from_paths("session_1", [str(runtime_file)])

        assert artifacts == []
    finally:
        runtime_file.unlink(missing_ok=True)


def test_create_artifacts_from_paths_ignores_runtime_skill_docs(tmp_path: Path):
    skill_doc = tmp_path / ".hermes" / "skills" / "SenseNova-Skills" / "docs" / "skill.md"
    skill_doc.parent.mkdir(parents=True, exist_ok=True)
    skill_doc.write_text("# Skill docs\n", encoding="utf-8")

    artifacts = create_artifacts_from_paths("session_1", [str(skill_doc)])

    assert artifacts == []


def test_create_artifacts_from_refs_preserves_openclaw_protocol_metadata(tmp_path: Path):
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


def test_create_artifacts_from_refs_marks_source_cache_as_intermediate(tmp_path: Path):
    source_cache = tmp_path / "source_cache"
    source_cache.mkdir()
    cache_file = source_cache / "jd_news.html"
    cache_file.write_text("<html><body>cached source</body></html>", encoding="utf-8")

    artifacts = create_artifacts_from_refs(
        "session_1",
        [
            AgentArtifactRef(
                path=str(cache_file),
                artifact_type="html_page",
                run_id="agent_run_1",
                source_dir=str(source_cache),
                title="jd_news",
            )
        ],
        run_id="webagent_run_1",
    )

    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.type == "html_page"
    assert artifact.metadata
    assert artifact.metadata["artifactRole"] == "intermediate"
    assert artifact.metadata["developerOnly"] is True
    assert artifact.metadata["originalPath"] == str(cache_file)


def test_discover_related_artifact_paths_finds_html_slides_for_pptx(tmp_path: Path):
    deck_dir = tmp_path / "ppt_decks"
    deck_dir.mkdir()
    deck = deck_dir / "deck.pptx"
    slide = deck_dir / "page_001.html"
    deck.write_bytes(b"pptx")
    slide.write_text("<html><body>slide</body></html>", encoding="utf-8")

    since = datetime.fromtimestamp(deck.stat().st_mtime) - timedelta(seconds=1)
    paths = discover_related_artifact_paths([str(deck)], since)

    normalized = {Path(path).name for path in paths}
    assert "deck.pptx" in normalized
    assert "page_001.html" in normalized


def test_create_artifacts_from_paths_marks_ppt_page_html_as_preview_fallback(tmp_path: Path):
    pages_dir = tmp_path / "ppt_decks" / "demo" / "pages"
    pages_dir.mkdir(parents=True)
    slide = pages_dir / "page_001.html"
    slide.write_text("<html><body>slide</body></html>", encoding="utf-8")

    artifacts = create_artifacts_from_paths("session_1", [str(slide)])

    assert len(artifacts) == 1
    assert artifacts[0].type == "html_page"
    assert artifacts[0].metadata
    assert artifacts[0].metadata["artifactRole"] == "preview_fallback"
    assert artifacts[0].metadata["developerOnly"] is False


def test_discover_related_artifact_paths_does_not_scan_repo_root(monkeypatch, tmp_path: Path):
    first = tmp_path / "first-report.md"
    second = tmp_path / "second-report.md"
    first.write_text("# First", encoding="utf-8")
    second.write_text("# Second", encoding="utf-8")
    monkeypatch.setattr("app.services.artifact_discovery._repo_root", lambda: tmp_path)

    since = datetime.fromtimestamp(first.stat().st_mtime) - timedelta(seconds=1)
    paths = discover_related_artifact_paths([str(first)], since)

    assert paths == []


def test_extract_artifact_path_strings_supports_relative_chinese_filename():
    paths = extract_artifact_path_strings(
        "HTML 已生成完成，结构验证通过。 ./城市夜间轻社交消费机会.html  可直接打开"
    )

    assert "./城市夜间轻社交消费机会.html" in paths


def test_extract_artifact_path_strings_supports_markdown_bold_filename():
    paths = extract_artifact_path_strings(
        "Created **ai-workflow-tools-small-teams.md** (1,443 words)."
    )

    assert "ai-workflow-tools-small-teams.md" in paths
