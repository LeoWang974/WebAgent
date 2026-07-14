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
async def test_runtime_context_builder_only_injects_supported_skills():
    content = "请研究未来餐桌"
    result = await build_runtime_content(
        FakeDb([artifact("未来餐桌报告", "markdown_report", "/home/demo/report.md")]),
        "session_1",
        content,
        "deep_research",
    )

    assert result == content


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

    context = result.split("Available artifacts: ", maxsplit=1)[1]
    assert "[WebAgent runtime context]" in result
    assert context.count(" -> ") == 6
    assert context.startswith("1. markdown_report: 未来餐桌深度研究报告")
    assert "plan.md" not in context
    assert ".hermes/skills" not in context
