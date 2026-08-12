from pathlib import Path

import pytest

from app import schemas
from app.core.config import settings
from app.models import Conversation
from app.services.agent_run_artifact_service import raise_for_fatal_runtime_diagnostics
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
        assert (tmp_path / "organized-artifacts").exists()
        assert Path(metadata["path"]).exists()
    finally:
        settings.artifact_storage_enabled = previous_enabled
        settings.artifact_storage_root = previous_root
