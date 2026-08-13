import json
from pathlib import Path

import pytest

from app import schemas
from app.core.config import settings
from app.models import Conversation
from app.services.agent_run_artifact_service import (
    filter_preexisting_artifact_schemas,
    raise_for_fatal_runtime_diagnostics,
    requested_primary_artifact_types,
    validate_requested_primary_artifacts,
)
from app.services.session_artifacts import metadata_path_key, organize_artifact_schema


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


def test_fatal_runtime_diagnostics_are_not_treated_as_success():
    with pytest.raises(RuntimeError, match="model/API failure"):
        raise_for_fatal_runtime_diagnostics(_Adapter(), "Hermes completed.")

    with pytest.raises(RuntimeError, match="model/API failure"):
        raise_for_fatal_runtime_diagnostics(_TruncatedAdapter(), "")


def test_requested_primary_artifact_types_only_match_explicit_output_requests():
    assert requested_primary_artifact_types(
        "Use the report at C:/input/source.md and generate a PPTX presentation."
    ) == {"ppt_deck"}
    assert requested_primary_artifact_types(
        "输出中文 Markdown 报告，然后生成 HTML 文件。"
    ) == {"markdown_report", "html_page"}
    assert requested_primary_artifact_types("Summarize the source.md file in chat.") == set()
    assert requested_primary_artifact_types(
        "请基于本对话刚生成的 Markdown 报告，生成一份中文 HTML 报告并保存为 .html 文件。"
    ) == {"html_page"}
    assert requested_primary_artifact_types(
        "Based on the generated Markdown report, create an English HTML report."
    ) == {"html_page"}


def test_filter_preexisting_artifacts_excludes_staged_input_by_hash(tmp_path):
    source = tmp_path / "source.md"
    output = tmp_path / "report.html"
    source.write_text("# Existing report", encoding="utf-8")
    output.write_text("<html>new</html>", encoding="utf-8")
    source_artifact = schemas.Artifact(
        id="source",
        session_id="conversation1",
        type="markdown_report",
        title="source",
        status="ready",
        metadata={
            "path": str(source),
            "contentHash": "existing-hash",
        },
    )
    output_artifact = schemas.Artifact(
        id="output",
        session_id="conversation1",
        type="html_page",
        title="report",
        status="ready",
        metadata={
            "path": str(output),
            "contentHash": "new-hash",
        },
    )

    filtered, excluded = filter_preexisting_artifact_schemas(
        [source_artifact, output_artifact],
        existing_hashes={"existing-hash"},
        existing_paths=set(),
    )

    assert filtered == [output_artifact]
    assert excluded == [str(source)]


def test_validate_requested_primary_artifacts_rejects_only_intermediate_outputs():
    intermediate = type(
        "ArtifactRecord",
        (),
        {
            "type": "markdown_report",
            "is_primary": False,
            "artifact_metadata": {"artifactRole": "intermediate"},
        },
    )()

    with pytest.raises(RuntimeError, match="markdown_report"):
        validate_requested_primary_artifacts(
            "Generate a Markdown report.",
            [intermediate],
        )

    validate_requested_primary_artifacts("Answer this question in chat.", [intermediate])


def test_organize_artifact_schema_keeps_metadata_path_existing(tmp_path):
    previous_enabled = settings.artifact_storage_enabled
    previous_root = settings.artifact_storage_root
    settings.artifact_storage_enabled = True
    settings.artifact_storage_root = str(tmp_path / "organized-artifacts")
    try:
        source = tmp_path / "agent-generated-deck.pptx"
        source.write_bytes(b"pptx")
        conversation = Conversation(
            id="conversation123456",
            user_id="user1",
            title="Hermes Test",
        )
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
        stored_path = Path(metadata["path"])
        expected_run_dir = (
            tmp_path
            / "organized-artifacts"
            / "users"
            / "user1"
            / "conversations"
            / conversation.id
            / "runs"
            / "runabcdef123456"
        )
        assert stored_path.parent == expected_run_dir / "primary"
        assert stored_path.exists()
        assert metadata["storageCategory"] == "primary"
        assert metadata["outputPathCompliant"] is False
        assert metadata["runtimeInstructionInjected"] is False

        manifest = json.loads((expected_run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["schema"] == "webagent.artifacts.v1"
        assert manifest["artifacts"][0]["artifactId"] == "artifact1"
        assert manifest["artifacts"][0]["storedPath"] == str(stored_path)
    finally:
        settings.artifact_storage_enabled = previous_enabled
        settings.artifact_storage_root = previous_root


def test_organize_artifact_schema_separates_intermediate_outputs(tmp_path):
    previous_enabled = settings.artifact_storage_enabled
    previous_root = settings.artifact_storage_root
    settings.artifact_storage_enabled = True
    settings.artifact_storage_root = str(tmp_path / "organized-artifacts")
    try:
        source = tmp_path / "plan.json"
        source.write_text('{"status":"ready"}', encoding="utf-8")
        conversation = Conversation(id="conversation1", user_id="user1", title="Test")
        artifact = schemas.Artifact(
            id="artifact-json",
            session_id=conversation.id,
            type="debug_json",
            title="plan",
            status="ready",
            metadata={"path": str(source), "developerOnly": True},
        )

        organized = organize_artifact_schema(artifact, conversation, "run1")
        metadata = organized.metadata or {}

        assert Path(metadata["path"]).parent.name == "intermediate"
        assert metadata["storageCategory"] == "intermediate"
        assert organized.is_primary is False
    finally:
        settings.artifact_storage_enabled = previous_enabled
        settings.artifact_storage_root = previous_root


def test_organize_artifact_schema_records_managed_runtime_output(tmp_path):
    previous_enabled = settings.artifact_storage_enabled
    previous_root = settings.artifact_storage_root
    previous_workspace_root = settings.agent_run_workspace_root
    settings.artifact_storage_enabled = True
    settings.artifact_storage_root = str(tmp_path / "organized-artifacts")
    settings.agent_run_workspace_root = str(tmp_path / "agent-runs")
    try:
        conversation = Conversation(id="conversation1", user_id="user1", title="Test")
        source = (
            tmp_path
            / "agent-runs"
            / "user1"
            / conversation.id
            / "run1"
            / "artifacts"
            / "report.md"
        )
        source.parent.mkdir(parents=True)
        source.write_text("# Report", encoding="utf-8")
        artifact = schemas.Artifact(
            id="artifact-report",
            session_id=conversation.id,
            type="markdown_report",
            title="report",
            status="ready",
            metadata={"path": str(source)},
        )

        organized = organize_artifact_schema(artifact, conversation, "run1")
        metadata = organized.metadata or {}

        assert metadata["sourceLocation"] == "run_workspace"
        assert metadata["outputPathCompliant"] is True
        assert metadata["runtimeInstructionInjected"] is False
    finally:
        settings.artifact_storage_enabled = previous_enabled
        settings.artifact_storage_root = previous_root
        settings.agent_run_workspace_root = previous_workspace_root
