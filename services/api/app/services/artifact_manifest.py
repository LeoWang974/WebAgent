# File purpose: Records, validates, and atomically persists Artifact Manifest v2 files.
# Main declarations: ArtifactManifestRecorder owns a run manifest; load_artifact_manifest reads it.

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.artifact_manifest import (
    ARTIFACT_MANIFEST_SCHEMA,
    ArtifactManifest,
    ArtifactManifestDiscoverySource,
    ArtifactManifestEntry,
    ArtifactManifestRole,
)

ARTIFACT_MANIFEST_FILENAME = "artifact-manifest.json"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry_id(path: str) -> str:
    normalized = path.strip().replace("\\", "/").lower()
    return hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()[:24]


def load_artifact_manifest(path: Path) -> ArtifactManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ArtifactManifest.model_validate(payload)


class ArtifactManifestRecorder:
    """Owns the canonical manifest for one adapter run."""

    def __init__(self, path: Path, *, run_id: str, conversation_id: str | None):
        now = _utc_now()
        self.path = path
        self.manifest = ArtifactManifest(
            run_id=run_id,
            conversation_id=conversation_id,
            created_at=now,
            updated_at=now,
        )
        self._write()

    def record(
        self,
        *,
        path: str,
        artifact_type: str,
        title: str,
        role: ArtifactManifestRole,
        discovered_by: ArtifactManifestDiscoverySource,
        source_dir: str | None,
        source_file: Path | None,
    ) -> ArtifactManifestEntry:
        ready = source_file is not None and source_file.is_file()
        size_bytes: int | None = None
        sha256: str | None = None
        if ready and source_file is not None:
            size_bytes = source_file.stat().st_size
            sha256 = _file_sha256(source_file)

        entry = ArtifactManifestEntry(
            entry_id=_entry_id(path),
            path=path,
            artifact_type=artifact_type,
            title=title,
            role=role,
            status="ready" if ready else "missing",
            discovered_by=discovered_by,
            source_dir=source_dir,
            size_bytes=size_bytes,
            sha256=sha256,
        )
        entries = [
            existing
            for existing in self.manifest.artifacts
            if existing.entry_id != entry.entry_id
        ]
        entries.append(entry)
        self.manifest.artifacts = entries
        self.manifest.recovery_used = (
            self.manifest.recovery_used or discovered_by == "recovery_scan"
        )
        self.manifest.updated_at = _utc_now()
        self._write()
        return entry

    def finalize(self, *, failed: bool = False, error: str | None = None) -> ArtifactManifest:
        now = _utc_now()
        self.manifest.status = "failed" if failed else "finalized"
        self.manifest.updated_at = now
        self.manifest.finalized_at = now
        if error and error not in self.manifest.errors:
            self.manifest.errors.append(error)
        self._write()
        return self.manifest

    def snapshot(self) -> dict[str, object]:
        return self.manifest.model_dump(mode="json", by_alias=True)

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        try:
            temporary.write_text(
                json.dumps(self.snapshot(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)


__all__ = [
    "ARTIFACT_MANIFEST_FILENAME",
    "ARTIFACT_MANIFEST_SCHEMA",
    "ArtifactManifestRecorder",
    "load_artifact_manifest",
]
