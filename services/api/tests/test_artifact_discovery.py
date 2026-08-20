# File purpose: Verifies test artifact discovery behavior and its regression contracts.
# Main declarations: test_windows_path_to_wsl_normalizes_backslashes verifies windows path to wsl
# normalizes backslashes; test_wsl_artifact_mtime_rejects_directories verifies wsl artifact mtime
# rejects directories; test_normalized_path_key_unifies_windows_and_wsl_paths verifies normalized
# path key unifies windows and wsl paths; test_configured_hermes_home_candidates_use_settings
# verifies configured hermes home candidates use settings;
# test_candidate_roots_include_hermes_deep_research_reports verifies candidate roots include
# hermes deep research reports; test_create_artifacts_from_paths_dedupes_by_content_hash verifies
# create artifacts from paths dedupes by content hash;
# test_create_artifacts_from_paths_ignores_runtime_dependency_docs verifies create artifacts from
# paths ignores runtime dependency docs;
# test_create_artifacts_from_paths_resolves_bare_filename_from_candidate_roots verifies create
# artifacts from paths resolves bare filename from candidate roots;
# test_create_artifacts_from_paths_resolves_bare_filename_from_api_workdir verifies create
# artifacts from paths resolves bare filename from api workdir;
# test_create_artifacts_from_paths_supports_debug_json verifies create artifacts from paths
# supports debug json; test_create_artifacts_from_paths_ignores_runtime_temp_json verifies create
# artifacts from paths ignores runtime temp json;
# test_create_artifacts_from_paths_accepts_run_scoped_runtime_report verifies create artifacts
# from paths accepts run scoped runtime report;
# test_create_artifacts_from_paths_accepts_agent_run_artifact verifies create artifacts from paths
# accepts agent run artifact; test_create_artifacts_from_paths_accepts_agent_run_root_artifact
# verifies create artifacts from paths accepts agent run root artifact;
# test_create_artifacts_from_paths_ignores_runtime_skill_docs verifies create artifacts from paths
# ignores runtime skill docs; test_explicit_run_skill_doc_is_developer_only verifies explicit run
# skill doc is developer only; test_hermes_runtime_soul_is_not_an_artifact verifies hermes runtime
# soul is not an artifact; test_create_artifacts_from_refs_preserves_hermes_protocol_metadata
# verifies create artifacts from refs preserves hermes protocol metadata;
# test_create_artifacts_from_refs_marks_source_cache_as_intermediate verifies create artifacts
# from refs marks source cache as intermediate;
# test_explicit_run_ref_accepts_primary_output_from_hermes_context verifies explicit run ref
# accepts primary output from hermes context;
# test_discover_related_artifact_paths_finds_html_slides_for_pptx verifies discover related
# artifact paths finds html slides for pptx;
# test_create_artifacts_from_paths_marks_ppt_page_html_as_preview_fallback verifies create
# artifacts from paths marks ppt page html as preview fallback;
# test_discover_related_artifact_paths_does_not_scan_repo_root verifies discover related artifact
# paths does not scan repo root;
# test_extract_artifact_path_strings_supports_relative_chinese_filename verifies extract artifact
# path strings supports relative chinese filename;
# test_extract_artifact_path_strings_supports_markdown_bold_filename verifies extract artifact
# path strings supports markdown bold filename.

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.core.config import settings
from app.integrations.hermes import AgentArtifactRef
from app.services.artifact_discovery import (
    _candidate_roots,
    _configured_hermes_home_candidates,
    _normalize_path,
    _normalized_path_key,
    _repo_root,
    _resolve_bare_artifact_filename,
    _windows_path_to_wsl,
    _wsl_artifact_mtime,
    create_artifacts_from_paths,
    create_artifacts_from_refs,
    discover_artifacts_with_retry,
    discover_related_artifact_paths,
    extract_artifact_path_strings,
)


def test_create_artifacts_archives_into_supplied_run_directory(tmp_path: Path):
    source = tmp_path / "external" / "report.md"
    source.parent.mkdir()
    source.write_text("# Report\n", encoding="utf-8")
    archive_dir = tmp_path / "users" / "user-1" / "runs" / "run-1" / "artifacts"

    artifacts = create_artifacts_from_paths(
        "session-1",
        [str(source)],
        "run-1",
        archive_dir=archive_dir,
    )

    assert len(artifacts) == 1
    assert artifacts[0].metadata
    assert Path(str(artifacts[0].metadata["path"])).parent == archive_dir.resolve()


@pytest.mark.asyncio
async def test_authoritative_manifest_discovery_skips_related_directory_scan(
    monkeypatch,
    tmp_path: Path,
):
    source = tmp_path / "report.md"
    source.write_text("# Manifest report\n", encoding="utf-8")

    def fail_related_scan(*args, **kwargs):
        raise AssertionError("authoritative manifest must not trigger related scans")

    monkeypatch.setattr(
        "app.services.artifact_discovery.discover_related_artifact_paths",
        fail_related_scan,
    )
    artifacts = await discover_artifacts_with_retry(
        "session-1",
        datetime.now(),
        [str(source)],
        "run-1",
        [
            AgentArtifactRef(
                path=str(source),
                artifact_type="markdown_report",
                run_id="run-1",
                source_dir=str(tmp_path),
                title="Manifest report",
            )
        ],
        archive_dir=tmp_path / "archive",
        authoritative_manifest=True,
    )

    assert [artifact.title for artifact in artifacts] == ["Manifest report"]


def test_windows_path_to_wsl_normalizes_backslashes(monkeypatch):
    monkeypatch.setattr("app.services.artifact_discovery.os.name", "nt")

    assert _windows_path_to_wsl(Path(r"D:\WebAgent\reports\deck.pptx")) == (
        "/mnt/d/WebAgent/reports/deck.pptx"
    )


def test_wsl_artifact_mtime_rejects_directories(monkeypatch):
    class Result:
        returncode = 0
        stdout = "directory:1786268343"

    monkeypatch.setattr("app.services.artifact_discovery.os.name", "nt")
    monkeypatch.setattr("app.services.artifact_discovery.shutil.which", lambda _: "wsl.exe")
    monkeypatch.setattr(
        "app.services.artifact_discovery.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    assert _wsl_artifact_mtime(Path(r"D:\WebAgent\reports")) is None


def test_normalized_path_key_unifies_windows_and_wsl_paths():
    assert _normalized_path_key(r"C:\Users\demo\report.md") == "/mnt/c/users/demo/report.md"
    assert (
        _normalized_path_key(r"\\wsl.localhost\Ubuntu\home\demo\report.md")
        == "/home/demo/report.md"
    )
    assert _normalized_path_key("/home/demo/report.md") == "/home/demo/report.md"
    assert (
        _normalized_path_key(r"\\wsl.localhost\Debian\home\demo\report.md")
        == "/home/demo/report.md"
    )


def test_configured_hermes_home_candidates_use_settings(monkeypatch, tmp_path: Path):
    hermes_home = tmp_path / "custom-hermes-home"
    monkeypatch.setattr(settings, "hermes_home", str(hermes_home))

    assert _configured_hermes_home_candidates() == [hermes_home]


def test_candidate_roots_include_hermes_deep_research_reports():
    roots = [str(root).replace("\\", "/") for root in _candidate_roots()]
    repo_root = str(_repo_root()).replace("\\", "/")

    assert any("/.hermes/deep-research-reports" in root for root in roots)
    assert f"{repo_root}/deep-research-reports" in roots


def test_reports_relative_path_resolves_from_repo_root():
    expected = _repo_root() / "reports" / "generated.md"

    assert _normalize_path("./reports/generated.md") == expected
    assert "./reports/generated.md" in extract_artifact_path_strings(
        "报告已保存到 ./reports/generated.md"
    )


def test_bare_repository_docs_are_not_resolved_as_artifacts():
    assert _resolve_bare_artifact_filename("README.md") is None
    assert _resolve_bare_artifact_filename("TESTING.md") is None


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


def test_create_artifacts_from_paths_ignores_runtime_dependency_docs(tmp_path: Path):
    package_license = (
        tmp_path
        / "hermes-home"
        / ".local"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "markdown-3.10.dist-info"
        / "licenses"
        / "LICENSE.md"
    )
    package_license.parent.mkdir(parents=True)
    package_license.write_text("dependency license", encoding="utf-8")

    assert create_artifacts_from_paths("session_1", [str(package_license)]) == []


def test_create_artifacts_from_paths_resolves_bare_filename_from_candidate_roots(
    monkeypatch,
    tmp_path: Path,
):
    workspace = tmp_path / ".hermes" / "workspace"
    workspace.mkdir(parents=True)
    deck = workspace / "Hermes回归测试_社区商业新机会.pptx"
    deck.write_bytes(b"pptx")
    monkeypatch.setattr(
        "app.services.artifact_discovery._candidate_roots",
        lambda: [workspace],
    )

    artifacts = create_artifacts_from_paths("session_1", [deck.name])

    assert len(artifacts) == 1
    assert artifacts[0].type == "ppt_deck"
    assert artifacts[0].metadata
    assert artifacts[0].metadata["path"] == str(deck)


def test_create_artifacts_from_paths_resolves_bare_filename_from_api_workdir(
    monkeypatch, tmp_path: Path
):
    report = tmp_path / "services" / "api" / "report.md"
    report.parent.mkdir(parents=True)
    report.write_text("# API workdir report\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.services.artifact_discovery._candidate_roots",
        lambda: [report.parent],
    )

    artifacts = create_artifacts_from_paths("session_1", [report.name])

    assert len(artifacts) == 1
    assert artifacts[0].content == "# API workdir report\n"
    assert artifacts[0].metadata["path"] == str(report)


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
    runtime_file = _repo_root() / "runtime" / "hermes_smoke_snapshot.json"
    try:
        runtime_file.parent.mkdir(parents=True, exist_ok=True)
        runtime_file.write_text('{"status":"running"}', encoding="utf-8")

        artifacts = create_artifacts_from_paths("session_1", [str(runtime_file)])

        assert artifacts == []
    finally:
        runtime_file.unlink(missing_ok=True)


def test_create_artifacts_from_paths_accepts_run_scoped_runtime_report(
    monkeypatch,
    tmp_path: Path,
):
    report = (
        tmp_path
        / "runtime"
        / "users"
        / "user_1"
        / "conversations"
        / "conversation_1"
        / "runs"
        / "run_1"
        / "hermes-home"
        / "reports"
        / "topic"
        / "report.md"
    )
    report.parent.mkdir(parents=True)
    report.write_text("# Current run report\n", encoding="utf-8")
    monkeypatch.setattr("app.services.artifact_discovery._repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "app.services.artifact_discovery._archive_artifact_path",
        lambda path, run_id, archive_dir=None: path,
    )

    artifacts = create_artifacts_from_paths("session_1", [str(report)], "run_1")

    assert len(artifacts) == 1
    assert artifacts[0].content == "# Current run report\n"
    assert artifacts[0].metadata
    assert artifacts[0].metadata["path"] == str(report)


def test_create_artifacts_from_paths_accepts_agent_run_artifact(
    monkeypatch,
    tmp_path: Path,
):
    report = tmp_path / "runtime" / "agent-runs" / "run_1" / "artifacts" / "report.html"
    report.parent.mkdir(parents=True)
    report.write_text("<html><body>Report</body></html>", encoding="utf-8")
    monkeypatch.setattr("app.services.artifact_discovery._repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "app.services.artifact_discovery._archive_artifact_path",
        lambda path, run_id, archive_dir=None: path,
    )

    artifacts = create_artifacts_from_paths("session_1", [str(report)], "run_1")

    assert len(artifacts) == 1
    assert artifacts[0].type == "html_page"
    assert artifacts[0].metadata
    assert artifacts[0].metadata["path"] == str(report)


def test_create_artifacts_from_paths_accepts_agent_run_root_artifact(
    monkeypatch,
    tmp_path: Path,
):
    deck = tmp_path / "runtime" / "agent-runs" / "run_1" / "report.pptx"
    deck.parent.mkdir(parents=True)
    deck.write_bytes(b"pptx")
    monkeypatch.setattr("app.services.artifact_discovery._repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "app.services.artifact_discovery._archive_artifact_path",
        lambda path, run_id, archive_dir=None: path,
    )

    artifacts = create_artifacts_from_paths("session_1", [str(deck)], "run_1")

    assert len(artifacts) == 1
    assert artifacts[0].type == "ppt_deck"
    assert artifacts[0].metadata
    assert artifacts[0].metadata["path"] == str(deck)


def test_create_artifacts_from_paths_ignores_runtime_skill_docs(tmp_path: Path):
    skill_doc = tmp_path / ".hermes" / "skills" / "SenseNova-Skills" / "docs" / "skill.md"
    skill_doc.parent.mkdir(parents=True, exist_ok=True)
    skill_doc.write_text("# Skill docs\n", encoding="utf-8")

    artifacts = create_artifacts_from_paths("session_1", [str(skill_doc)])

    assert artifacts == []


def test_explicit_run_skill_doc_is_developer_only(tmp_path: Path):
    skill_doc = tmp_path / "hermes-home" / "skills" / "sn-ppt-standard" / "SKILL.md"
    skill_doc.parent.mkdir(parents=True)
    skill_doc.write_text("# Runtime skill instructions\n", encoding="utf-8")

    artifacts = create_artifacts_from_paths("session_1", [str(skill_doc)], "run_1")

    assert len(artifacts) == 1
    assert artifacts[0].metadata
    assert artifacts[0].metadata["artifactRole"] == "intermediate"
    assert artifacts[0].metadata["developerOnly"] is True
    assert artifacts[0].is_primary is False


def test_hermes_runtime_soul_is_not_an_artifact(tmp_path: Path):
    soul = tmp_path / "hermes-home" / "SOUL.md"
    soul.parent.mkdir(parents=True)
    soul.write_text("# Runtime persona\n", encoding="utf-8")

    artifacts = create_artifacts_from_paths("session_1", [str(soul)], "run_1")

    assert artifacts == []


def test_create_artifacts_from_refs_preserves_hermes_protocol_metadata(tmp_path: Path):
    report = tmp_path / "hermes-report.md"
    report.write_text("# Hermes Report\n", encoding="utf-8")

    artifacts = create_artifacts_from_refs(
        "session_1",
        [
            AgentArtifactRef(
                path=str(report),
                artifact_type="markdown_report",
                run_id="hermes_run_1",
                source_dir=str(tmp_path),
                title="Hermes 标准报告",
            )
        ],
        run_id="webagent_run_1",
    )

    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.type == "markdown_report"
    assert artifact.title == "Hermes 标准报告"
    assert artifact.content == "# Hermes Report\n"
    assert artifact.metadata
    assert artifact.metadata["adapterProtocol"] == "hermes.artifact.v1"
    assert artifact.metadata["adapterRunId"] == "hermes_run_1"
    assert artifact.metadata["adapterSourceDir"] == str(tmp_path)
    assert artifact.metadata["adapterTitle"] == "Hermes 标准报告"
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


def test_explicit_run_ref_accepts_primary_output_from_hermes_context(
    monkeypatch,
    tmp_path: Path,
):
    output = (
        tmp_path
        / "runtime"
        / "users"
        / "user_1"
        / "conversations"
        / "conversation_1"
        / "runs"
        / "run_1"
        / "hermes-home"
        / "context"
        / "report.html"
    )
    output.parent.mkdir(parents=True)
    output.write_text("<html lang='zh-CN'><body>final report</body></html>", encoding="utf-8")
    archive_dir = tmp_path / "archive" / "run_1"
    archive_dir.mkdir(parents=True)
    monkeypatch.setattr("app.services.artifact_discovery._repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "app.services.artifact_discovery._runtime_artifacts_dir",
        lambda run_id: archive_dir,
    )

    artifacts = create_artifacts_from_refs(
        "session_1",
        [
            AgentArtifactRef(
                path=str(output),
                artifact_type="html_page",
                run_id="run_1",
                source_dir=str(output.parent),
                title="Final report",
            )
        ],
        run_id="run_1",
    )

    assert len(artifacts) == 1
    assert artifacts[0].type == "html_page"
    assert artifacts[0].metadata
    assert artifacts[0].metadata["originalPath"] == str(output)


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
