# File purpose: Verifies Artifact Manifest v3 states, integrity, and v2 read compatibility.
# Main declarations: tests cover state finalization, file refresh, and checksum validation.

import hashlib
import json
from pathlib import Path

import pytest

from app.services.artifact_discovery import create_artifacts_from_refs
from app.services.artifact_manifest import ArtifactManifestRecorder, load_artifact_manifest


def test_manifest_recorder_finalizes_ready_artifact(tmp_path: Path):
    output = tmp_path / "report.md"
    output.write_text("# Report\n", encoding="utf-8")
    manifest_path = tmp_path / "artifact-manifest.json"
    recorder = ArtifactManifestRecorder(
        manifest_path,
        run_id="run-1",
        conversation_id="conversation-1",
    )

    entry = recorder.record(
        path=str(output),
        artifact_type="markdown_report",
        title="Report",
        role="primary",
        discovered_by="adapter_event",
        source_dir=str(tmp_path),
        source_file=output,
    )
    recorder.finalize()

    manifest = load_artifact_manifest(manifest_path)
    assert manifest.schema_version == "webagent.artifacts.v3"
    assert manifest.status == "finalized"
    assert manifest.finalized_at is not None
    assert manifest.artifacts == [entry]
    assert entry.status == "ready"
    assert entry.size_bytes == output.stat().st_size
    assert entry.sha256 == hashlib.sha256(output.read_bytes()).hexdigest()


def test_manifest_recorder_refreshes_missing_entry_when_file_appears(tmp_path: Path):
    output = tmp_path / "deck.pptx"
    recorder = ArtifactManifestRecorder(
        tmp_path / "artifact-manifest.json",
        run_id="run-1",
        conversation_id="conversation-1",
    )

    missing = recorder.record(
        path=str(output),
        artifact_type="ppt_deck",
        title="Deck",
        role="primary",
        discovered_by="terminal_output",
        source_dir=str(tmp_path),
        source_file=None,
    )
    output.write_bytes(b"pptx")
    ready = recorder.record(
        path=str(output),
        artifact_type="ppt_deck",
        title="Deck",
        role="primary",
        discovered_by="terminal_output",
        source_dir=str(tmp_path),
        source_file=output,
    )

    assert missing.entry_id == ready.entry_id
    assert ready.status == "ready"
    assert recorder.manifest.artifacts == [ready]


def test_manifest_finalization_fails_unsettled_entry(tmp_path: Path):
    recorder = ArtifactManifestRecorder(
        tmp_path / "artifact-manifest.json",
        run_id="run-1",
        conversation_id="conversation-1",
    )
    recorder.record(
        path=str(tmp_path / "report.md"),
        artifact_type="markdown_report",
        title="Report",
        role="primary",
        discovered_by="file_watcher",
        source_dir=str(tmp_path),
        source_file=None,
        status="staging",
    )

    manifest = recorder.finalize()

    assert manifest.artifacts[0].status == "failed"
    assert "before the file became stable" in str(manifest.artifacts[0].error)


def test_load_manifest_keeps_v2_compatibility(tmp_path: Path):
    path = tmp_path / "artifact-manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema": "webagent.artifacts.v2",
                "run_id": "legacy-run",
                "producer": "hermes_cli_adapter",
                "status": "finalized",
                "created_at": "2026-08-19T10:00:00Z",
                "updated_at": "2026-08-19T10:00:01Z",
                "artifacts": [],
            }
        ),
        encoding="utf-8",
    )

    assert load_artifact_manifest(path).schema_version == "webagent.artifacts.v2"


def test_manifest_ref_integrity_is_preserved_in_artifact_metadata(tmp_path: Path):
    output = tmp_path / "report.html"
    output.write_text("<html><body>ready</body></html>", encoding="utf-8")
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()

    artifacts = create_artifacts_from_refs(
        "conversation-1",
        [
            {
                "path": str(output),
                "artifact_type": "html_page",
                "run_id": "run-1",
                "source_dir": str(tmp_path),
                "title": "Report",
                "entry_id": "entry-1",
                "role": "primary",
                "status": "ready",
                "discovered_by": "adapter_event",
                "size_bytes": output.stat().st_size,
                "sha256": checksum,
                "manifest_schema": "webagent.artifacts.v3",
                "manifest_path": str(tmp_path / "artifact-manifest.json"),
            }
        ],
    )

    assert len(artifacts) == 1
    metadata = artifacts[0].metadata or {}
    assert metadata["adapterProtocol"] == "webagent.artifacts.v3"
    assert metadata["manifestEntryId"] == "entry-1"
    assert metadata["manifestIntegrityVerified"] is True
    assert metadata["manifestDiscoveredBy"] == "adapter_event"


def test_manifest_ref_rejects_checksum_mismatch(tmp_path: Path):
    output = tmp_path / "report.md"
    output.write_text("# Changed\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        create_artifacts_from_refs(
            "conversation-1",
            [
                {
                    "path": str(output),
                    "artifact_type": "markdown_report",
                    "status": "ready",
                    "size_bytes": output.stat().st_size,
                    "sha256": "0" * 64,
                    "manifest_schema": "webagent.artifacts.v3",
                }
            ],
        )
