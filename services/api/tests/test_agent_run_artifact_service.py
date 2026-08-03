import pytest

from app.services.agent_run_artifact_service import (
    raise_for_fatal_runtime_diagnostics,
    requested_primary_artifact_types,
    validate_primary_artifacts,
)


class _Artifact:
    def __init__(
        self,
        artifact_type: str,
        metadata: dict | None = None,
    ):
        self.type = artifact_type
        self.artifact_metadata = metadata or {}


class _Adapter:
    last_diagnostics = {
        "stderr_tail": "RateLimitError: HTTP 429 rpm exhausted",
        "stdout_tail": "",
        "last_stage": "API call failed after 3 retries",
    }


class _TruncatedAdapter:
    last_diagnostics = {
        "stderr_tail": "",
        "stdout_tail": "Response truncated due to output length limit",
        "last_stage": "Truncated tool call response detected again",
    }


def test_requested_primary_artifact_types_from_user_prompt():
    assert requested_primary_artifact_types("输出中文 Markdown 报告") == {"markdown_report"}
    assert requested_primary_artifact_types("生成一份12页PPT，全过程自己决策") == {"ppt_deck"}
    assert requested_primary_artifact_types("使用 report-html-v2 输出 HTML 文件") == {"html_page"}
    assert requested_primary_artifact_types("输出中文纯 Markdown 报告，不要混合 HTML 格式") == {
        "markdown_report"
    }
    assert requested_primary_artifact_types("请使用上述 Markdown 报告生成完整 HTML 文件") == {
        "html_page"
    }
    assert requested_primary_artifact_types(
        "请使用上述 Markdown 报告和 HTML 文件生成 6 页 PPT"
    ) == {
        "ppt_deck"
    }
    assert requested_primary_artifact_types("输出 Markdown 报告，包含一个对比表格") == {
        "markdown_report"
    }


def test_validate_primary_artifacts_uses_user_prompt_when_skill_key_is_empty():
    with pytest.raises(RuntimeError, match="completed without producing a primary artifact"):
        validate_primary_artifacts(None, [], "请输出中文 Markdown 报告")

    validate_primary_artifacts(None, [_Artifact("markdown_report")], "请输出中文 Markdown 报告")


def test_validate_primary_artifacts_ignores_intermediate_markdown():
    intermediate_markdown = _Artifact(
        "markdown_report",
        {"developerOnly": True, "artifactRole": "intermediate"},
    )

    with pytest.raises(RuntimeError, match="completed without producing a primary artifact"):
        validate_primary_artifacts(None, [intermediate_markdown], "请输出中文 Markdown 报告")


def test_fatal_runtime_diagnostics_are_not_treated_as_success():
    with pytest.raises(RuntimeError, match="model/API failure"):
        raise_for_fatal_runtime_diagnostics(
            _Adapter(),
            "Hermes completed. Discovering generated artifacts.",
        )

    with pytest.raises(RuntimeError, match="model/API failure"):
        raise_for_fatal_runtime_diagnostics(_TruncatedAdapter(), "")
