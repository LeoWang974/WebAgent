# File purpose: Verifies test agent run artifact service behavior and its regression contracts.
# Main declarations: _Adapter defines adapter state or behavior; _TruncatedAdapter defines
# truncated adapter state or behavior; test_fatal_runtime_diagnostics_are_not_treated_as_success
# verifies fatal runtime diagnostics are not treated as success;
# test_fatal_runtime_diagnostics_do_not_match_unrelated_401_text verifies fatal runtime
# diagnostics do not match unrelated 401 text;
# test_fatal_runtime_diagnostics_match_explicit_http_401 verifies fatal runtime diagnostics match
# explicit http 401;
# test_organize_artifact_schema_keeps_metadata_path_existing verifies organize artifact schema
# keeps metadata path existing; test_organize_artifact_schema_separates_intermediate_outputs
# verifies organize artifact schema separates intermediate outputs;
# test_organize_artifact_schema_records_managed_runtime_output verifies organize artifact schema
# records managed runtime output.

import json
from inspect import signature
from pathlib import Path

import pytest

from app import schemas
from app.core.config import settings
from app.models import Artifact, Conversation
from app.services.agent_run_artifact_service import (
    discover_and_persist_run_artifacts,
    final_assistant_message,
    raise_for_fatal_runtime_diagnostics,
)
from app.services.session_artifacts import (
    _artifact_match_keys,
    artifact_content_hash,
    metadata_path_key,
    organize_artifact_schema,
)


def test_artifact_content_hash_does_not_mutate_metadata(tmp_path: Path):
    output = tmp_path / "report.md"
    output.write_text("# Report\n", encoding="utf-8")
    artifact = Artifact(
        conversation_id="conversation-1",
        type="markdown_report",
        title="Report",
        status="ready",
        artifact_metadata={"path": str(output)},
    )

    assert artifact_content_hash(artifact)
    assert artifact.artifact_metadata == {"path": str(output)}


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


def test_fatal_runtime_diagnostics_do_not_match_unrelated_401_text():
    adapter = type(
        "Adapter",
        (),
        {"last_diagnostics": {"last_stage": "Reviewed 401 records successfully."}},
    )()
    raise_for_fatal_runtime_diagnostics(adapter, "The report contains 401 survey responses.")


def test_fatal_runtime_diagnostics_match_explicit_http_401():
    adapter = type(
        "Adapter",
        (),
        {"last_diagnostics": {"stderr_tail": "HTTP status 401: Unauthorized"}},
    )()
    with pytest.raises(RuntimeError, match="model/API failure"):
        raise_for_fatal_runtime_diagnostics(adapter, "")


def test_fatal_runtime_diagnostics_match_stalled_tool_call():
    adapter = type("Adapter", (), {"last_diagnostics": {}})()
    with pytest.raises(RuntimeError, match="model/API failure"):
        raise_for_fatal_runtime_diagnostics(
            adapter,
            "Stream stalled mid tool-call; the action was not executed.",
        )


@pytest.mark.asyncio
async def test_final_assistant_message_does_not_use_stage_message_when_artifacts_exist(
    monkeypatch,
):
    stage_message = object()
    persisted_message = object()

    async def fake_persist_message(*args, **kwargs):
        return persisted_message

    monkeypatch.setattr(
        "app.services.agent_run_artifact_service.persist_message",
        fake_persist_message,
    )

    result = await final_assistant_message(
        db=object(),
        conversation_id="conversation-1",
        assistant_messages=[stage_message],
        response_artifacts=[type("Artifact", (), {"id": "artifact-1"})()],
        completion_messages=[],
    )

    assert result is persisted_message


@pytest.mark.asyncio
async def test_final_assistant_message_prefers_explicit_completion_message(
    monkeypatch,
):
    stage_message = object()
    completion_message = type("Message", (), {"artifact_ids": []})()

    class FakeDb:
        async def flush(self):
            return None

        async def refresh(self, message):
            return None

    result = await final_assistant_message(
        db=FakeDb(),
        conversation_id="conversation-1",
        assistant_messages=[stage_message],
        response_artifacts=[type("Artifact", (), {"id": "artifact-1"})()],
        completion_messages=[completion_message],
    )

    assert result is completion_message
    assert completion_message.artifact_ids == ["artifact-1"]


def test_artifact_discovery_does_not_accept_user_prompt_content():
    assert "content" not in signature(discover_and_persist_run_artifacts).parameters


def test_manifest_entry_identity_does_not_use_cross_run_content_hash():
    metadata = {
        "adapterProtocol": "webagent.artifacts.v3",
        "manifestEntryId": "entry-1",
        "contentHash": "same-content-as-an-older-run",
        "originalPath": "/reports/report.md",
    }

    assert _artifact_match_keys(metadata) == {"manifest:entry-1"}


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
