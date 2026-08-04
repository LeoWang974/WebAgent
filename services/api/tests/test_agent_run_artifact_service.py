import pytest
from pathlib import Path

from app import schemas
from app.core.config import settings
from app.models import Conversation
from app.services.agent_run_artifact_service import (
    delayed_discovery_attempts,
    raise_for_fatal_runtime_diagnostics,
    requested_primary_artifact_types,
    source_artifact_types_for_request,
    validate_primary_artifacts,
)
from app.services.session_artifacts import organize_artifact_schema
from app.services.session_artifacts import metadata_path_key


class _Artifact:
    def __init__(
        self,
        artifact_type: str,
        metadata: dict | None = None,
        is_primary: bool = True,
    ):
        self.type = artifact_type
        self.artifact_metadata = metadata or {}
        self.is_primary = is_primary


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


def test_source_artifact_types_follow_artifact_chain():
    assert source_artifact_types_for_request({"html_page"}, None) == {"markdown_report"}
    assert source_artifact_types_for_request({"ppt_deck"}, None) == {
        "html_page",
        "markdown_report",
    }
    assert source_artifact_types_for_request(set(), "html_generation") == {"markdown_report"}
    assert source_artifact_types_for_request(set(), "ppt_generation") == {
        "html_page",
        "markdown_report",
    }


def test_delayed_discovery_waits_for_html_and_ppt_outputs():
    assert delayed_discovery_attempts({"html_page"}) >= 6
    assert delayed_discovery_attempts({"ppt_deck"}) >= 10


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


def test_organize_artifact_schema_keeps_metadata_path_existing(tmp_path):
    previous_enabled = settings.artifact_storage_enabled
    previous_root = settings.artifact_storage_root
    settings.artifact_storage_enabled = True
    settings.artifact_storage_root = str(tmp_path / "organized-artifacts")
    try:
        source = tmp_path / "agent-generated-deck.pptx"
        source.write_bytes(b"pptx")
        conversation = Conversation(id="conversation123456", user_id="user1", title="OpenClaw Test")
        artifact = schemas.Artifact(
            id="artifact1",
            session_id=conversation.id,
            type="ppt_deck",
            title="agent-generated-deck",
            status="ready",
            metadata={
                "path": str(source),
                "normalizedPath": str(source).replace("\\", "/").lower(),
                "contentHash": "hash",
            },
        )

        organized = organize_artifact_schema(artifact, conversation, "runabcdef123456")
        metadata = organized.metadata or {}

        assert metadata["path"] != str(source)
        assert metadata["originalPath"] == str(source)
        assert metadata["normalizedPath"] == metadata_path_key(metadata["path"])
        assert (tmp_path / "organized-artifacts").exists()
        assert Path(metadata["path"]).exists()
    finally:
        settings.artifact_storage_enabled = previous_enabled
        settings.artifact_storage_root = previous_root
