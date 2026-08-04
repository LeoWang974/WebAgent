from types import SimpleNamespace

import pytest

from app.services import runtime_environment
from app.services.artifact_context_builder import (
    artifact_quality_score,
    build_runtime_content,
    normalize_runtime_path,
)
from app.services.runtime_environment import build_user_runtime_context


class FakeScalars:
    def __init__(self, artifacts):
        self.artifacts = artifacts

    def all(self):
        return self.artifacts


class FakeResult:
    def __init__(self, artifacts):
        self.artifacts = artifacts

    def scalars(self):
        return FakeScalars(self.artifacts)


class FakeDb:
    def __init__(self, artifacts):
        self.artifacts = artifacts

    async def execute(self, _statement):
        return FakeResult(self.artifacts)


def artifact(title, artifact_type, path):
    return SimpleNamespace(
        artifact_metadata={"path": path},
        title=title,
        type=artifact_type,
    )


def test_normalize_runtime_path_handles_windows_and_wsl_paths():
    assert normalize_runtime_path(r"C:\Users\demo\report.md") == "/mnt/c/Users/demo/report.md"
    assert (
        normalize_runtime_path(r"\\wsl.localhost\Ubuntu\home\demo\report.md")
        == "/home/demo/report.md"
    )
    assert normalize_runtime_path("/home/demo/report.md") == "/home/demo/report.md"


def test_artifact_quality_score_uses_path_and_type_not_chinese_title():
    score = artifact_quality_score(
        artifact("theme-park-market", "markdown_report", "/home/demo/theme-park-report.md"),
        "/home/demo/theme-park-report.md",
    )

    assert score >= 40


@pytest.mark.asyncio
async def test_artifact_context_builder_injects_limited_deep_research_context():
    result = await build_runtime_content(
        FakeDb(
            [
                artifact("未来餐桌报告", "markdown_report", "/home/demo/report.md"),
                artifact("page", "html_page", "/home/demo/page.html"),
                artifact("table", "data_table", "/home/demo/table.csv"),
                artifact("extra", "chart", "/home/demo/chart.csv"),
            ]
        ),
        "session_1",
        "请研究《未来餐桌》",
        "deep_research",
    )

    context = result.split("[WebAgent related artifacts: hermes]", maxsplit=1)[1]
    assert "Available artifacts" not in result
    assert context.count(" -> ") == 3
    assert "未来餐桌报告" in context


@pytest.mark.asyncio
async def test_artifact_context_builder_prioritizes_final_reports_and_limits_paths():
    artifacts = [
        artifact("plan", "markdown_report", "/home/demo/reports/plan.md"),
        artifact("未来餐桌深度研究报告", "markdown_report", "/home/demo/reports/report.md"),
        artifact("page_001", "html_page", "/home/demo/ppt_decks/pages/page_001.html"),
        artifact("page_002", "html_page", "/home/demo/ppt_decks/pages/page_002.html"),
        artifact("page_003", "html_page", "/home/demo/ppt_decks/pages/page_003.html"),
        artifact("page_004", "html_page", "/home/demo/ppt_decks/pages/page_004.html"),
        artifact("page_005", "html_page", "/home/demo/ppt_decks/pages/page_005.html"),
        artifact("page_006", "html_page", "/home/demo/ppt_decks/pages/page_006.html"),
        artifact("ignored", "markdown_report", "/home/demo/.hermes/skills/sn/report.md"),
    ]

    result = await build_runtime_content(
        FakeDb(artifacts),
        "session_1",
        "请使用《未来餐桌》报告生成 PPT",
        "ppt_generation",
    )

    context = result.split("[WebAgent related artifacts: hermes]", maxsplit=1)[1]
    assert context.count(" -> ") == 6
    assert "1. markdown_report: 未来餐桌深度研究报告" in context
    assert "plan.md" not in context
    artifact_lines = [line for line in context.splitlines() if " -> " in line]
    assert all(".hermes/skills" not in line for line in artifact_lines)


@pytest.mark.asyncio
async def test_artifact_context_builder_uses_openclaw_context_style_and_limits_paths():
    result = await build_runtime_content(
        FakeDb(
            [
                artifact("未来餐桌报告", "markdown_report", "/home/demo/report.md"),
                artifact("deck", "ppt_deck", "/home/demo/deck.pptx"),
                artifact("page", "html_page", "/home/demo/page.html"),
                artifact("table", "data_table", "/home/demo/table.csv"),
            ]
        ),
        "session_1",
        "最后请基于《未来餐桌》报告生成 PPT",
        "ppt_generation",
        "openclaw",
    )

    assert "[WebAgent related artifacts: openclaw]" in result
    assert "OpenClaw context" not in result
    assert "artifact_1: type=markdown_report" in result
    assert result.count("path=") == 3
    assert "artifact_4" not in result


@pytest.mark.asyncio
async def test_artifact_context_builder_injects_markdown_for_openclaw_html_generation():
    result = await build_runtime_content(
        FakeDb(
            [
                artifact("二次元正在改变消费市场", "markdown_report", "/home/demo/report.md"),
                artifact("old-page", "html_page", "/home/demo/old.html"),
                artifact("deck", "ppt_deck", "/home/demo/deck.pptx"),
            ]
        ),
        "session_1",
        "请使用上述生成的《二次元正在改变消费市场》markdown报告。使用report-html-v2为我输出HTML文件",
        "html_generation",
        "openclaw",
    )

    assert "[WebAgent related artifacts: openclaw]" in result
    assert "WebAgent selected a few relevant markdown_report paths" not in result
    assert "artifact_1: type=markdown_report" in result
    assert "path=/home/demo/report.md" in result
    assert result.count("path=") == 2


def test_user_runtime_context_copies_openclaw_gateway_config(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.joinpath(".openclaw").mkdir(parents=True)
    fake_home.joinpath(".openclaw", "openclaw.json").write_text(
        '{"gateway":{"auth":{"mode":"token","token":"test-token"}}}',
        encoding="utf-8",
    )
    fake_home.joinpath(".openclaw", ".env").write_text("OPENCLAW_TEST=1\n", encoding="utf-8")

    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    hermes_home.joinpath(".env").write_text("SERPER_API_KEY=test\n", encoding="utf-8")
    hermes_home.joinpath("skills").mkdir()
    openclaw_skills = tmp_path / "openclaw-skills"
    openclaw_skills.mkdir()

    monkeypatch.setattr(runtime_environment.Path, "home", lambda: fake_home)
    monkeypatch.setattr(
        runtime_environment.settings,
        "agent_runtime_user_root",
        str(tmp_path / "runtime"),
    )
    monkeypatch.setattr(runtime_environment.settings, "hermes_home", str(hermes_home))
    monkeypatch.setattr(
        runtime_environment.settings,
        "hermes_skills_dir",
        str(hermes_home / "skills"),
    )
    monkeypatch.setattr(
        runtime_environment.settings,
        "openclaw_skills_dir",
        str(openclaw_skills),
    )

    context = build_user_runtime_context(
        SimpleNamespace(id="user-1"),
        "conversation-1",
        run_id="run-1",
    )

    copied_config = context.openclaw_home / ".openclaw" / "openclaw.json"
    copied_env = context.openclaw_home / ".openclaw" / ".env"
    assert copied_config.read_text(encoding="utf-8") == (
        '{"gateway":{"auth":{"mode":"token","token":"test-token"}}}'
    )
    copied_env_text = copied_env.read_text(encoding="utf-8")
    assert "OPENCLAW_TEST=1" in copied_env_text
    assert "OPENCLAW_GATEWAY_TOKEN=test-token" in copied_env_text
    assert "OPENCLAW_GATEWAY_AUTH_TOKEN=test-token" in copied_env_text
    assert "OPENCLAW_TOKEN=test-token" in copied_env_text


def test_user_runtime_context_does_not_write_openclaw_gateway_url_without_token(
    tmp_path,
    monkeypatch,
):
    fake_home = tmp_path / "home"
    fake_home.joinpath(".openclaw").mkdir(parents=True)
    fake_home.joinpath(".openclaw", "openclaw.json").write_text(
        '{"gateway":{"auth":{"mode":"none"}}}',
        encoding="utf-8",
    )
    fake_home.joinpath(".openclaw", ".env").write_text("OPENCLAW_TEST=1\n", encoding="utf-8")

    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    hermes_home.joinpath(".env").write_text("SERPER_API_KEY=test\n", encoding="utf-8")
    hermes_home.joinpath("skills").mkdir()
    openclaw_skills = tmp_path / "openclaw-skills"
    openclaw_skills.mkdir()

    monkeypatch.setenv("OPENCLAW_GATEWAY_URL", "ws://127.0.0.1:18789")
    monkeypatch.setattr(runtime_environment.Path, "home", lambda: fake_home)
    monkeypatch.setattr(
        runtime_environment.settings,
        "agent_runtime_user_root",
        str(tmp_path / "runtime"),
    )
    monkeypatch.setattr(runtime_environment.settings, "hermes_home", str(hermes_home))
    monkeypatch.setattr(
        runtime_environment.settings,
        "hermes_skills_dir",
        str(hermes_home / "skills"),
    )
    monkeypatch.setattr(
        runtime_environment.settings,
        "openclaw_skills_dir",
        str(openclaw_skills),
    )

    context = build_user_runtime_context(
        SimpleNamespace(id="user-1"),
        "conversation-1",
        run_id="run-1",
    )

    copied_env_text = (context.openclaw_home / ".openclaw" / ".env").read_text(
        encoding="utf-8",
    )
    assert "OPENCLAW_TEST=1" in copied_env_text
    assert "OPENCLAW_GATEWAY_URL=" not in copied_env_text
