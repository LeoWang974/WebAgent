from types import SimpleNamespace

import pytest

from app.services.runtime_context_builder import build_runtime_content, normalize_runtime_path


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


@pytest.mark.asyncio
async def test_runtime_context_builder_injects_limited_deep_research_context():
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

    context = result.split("[WebAgent runtime context: hermes]", maxsplit=1)[1]
    assert "Available artifacts" not in result
    assert context.count(" -> ") == 3
    assert "未来餐桌报告" in context


@pytest.mark.asyncio
async def test_runtime_context_builder_prioritizes_final_reports_and_limits_paths():
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

    context = result.split("[WebAgent runtime context: hermes]", maxsplit=1)[1]
    assert context.count(" -> ") == 6
    assert "1. markdown_report: 未来餐桌深度研究报告" in context
    assert "plan.md" not in context
    assert ".hermes/skills" not in context


@pytest.mark.asyncio
async def test_runtime_context_builder_uses_openclaw_context_style_and_limits_paths():
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

    assert "[WebAgent runtime context: openclaw]" in result
    assert "OpenClaw context" in result
    assert "artifact_1: type=markdown_report" in result
    assert result.count("path=") == 3
    assert "artifact_4" not in result


@pytest.mark.asyncio
async def test_runtime_context_builder_injects_markdown_for_openclaw_html_generation():
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

    assert "[WebAgent runtime context: openclaw]" in result
    assert "report-html-v2 workflow" in result
    assert "artifact_1: type=markdown_report" in result
    assert "path=/home/demo/report.md" in result
    assert result.count("path=") == 2
