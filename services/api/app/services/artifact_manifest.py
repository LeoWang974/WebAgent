# File purpose: Records, validates, and atomically persists Artifact Manifest v3 files.
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
    ArtifactManifestEntryStatus,
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
    normalized = path.strip().replace("\\", "/")
    return hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()[:24]


def load_artifact_manifest(path: Path) -> ArtifactManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ArtifactManifest.model_validate(payload)


class ArtifactManifestRecorder:
    """Owns the canonical manifest for one adapter run."""

    def __init__(
        self,
        path: Path,
        *,
        run_id: str,
        conversation_id: str | None,
        workspace_dir: str | None = None,
        artifacts_dir: str | None = None,
    ):
        now = _utc_now()
        self.path = path
        self.manifest = ArtifactManifest(
            run_id=run_id,
            conversation_id=conversation_id,
            workspace_dir=workspace_dir,
            artifacts_dir=artifacts_dir,
            created_at=now,
            updated_at=now,
        )
        self._entries_by_id: dict[str, ArtifactManifestEntry] = {}
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
        status: ArtifactManifestEntryStatus | None = None,
        size_bytes: int | None = None,
        mtime_ns: int | None = None,
        stable_at: datetime | None = None,
        error: str | None = None,
    ) -> ArtifactManifestEntry:
        now = _utc_now()
        entry_id = _entry_id(path)
        existing = self._entries_by_id.get(entry_id)
        ready = status == "ready" or (status is None and source_file is not None)
        sha256: str | None = None
        if ready and (source_file is None or not source_file.is_file()):
            ready = False
            status = "failed"
            error = error or "Artifact path was reported but no readable file was available."
        if ready and source_file is not None:
            try:
                stat = source_file.stat()
                size_bytes = stat.st_size
                mtime_ns = stat.st_mtime_ns
                sha256 = _file_sha256(source_file)
            except OSError as file_error:
                ready = False
                status = "failed"
                error = str(file_error)

        resolved_status = status or ("ready" if ready else "failed")
        path_scope = "unknown"
        if source_file is not None:
            resolved_source = source_file.resolve()
            managed_roots = [
                Path(root).expanduser().resolve()
                for root in (self.manifest.workspace_dir, self.manifest.artifacts_dir)
                if root
            ]
            path_scope = (
                "managed"
                if any(resolved_source.is_relative_to(root) for root in managed_roots)
                else "external"
            )

        entry = ArtifactManifestEntry(
            entry_id=entry_id,
            path=path,
            artifact_type=artifact_type,
            title=title,
            role=role,
            status=resolved_status,
            discovered_by=discovered_by,
            source_dir=source_dir,
            path_scope=path_scope,
            size_bytes=size_bytes,
            mtime_ns=mtime_ns,
            sha256=sha256,
            first_seen_at=existing.first_seen_at if existing else now,
            stable_at=stable_at if resolved_status == "ready" else None,
            error=error,
        )
        entries = [
            existing
            for existing in self.manifest.artifacts
            if existing.entry_id != entry.entry_id
        ]
        entries.append(entry)
        self.manifest.artifacts = entries
        self._entries_by_id[entry.entry_id] = entry
        self.manifest.recovery_used = (
            self.manifest.recovery_used or discovered_by == "recovery_scan"
        )
        self.manifest.updated_at = _utc_now()
        self._write()
        return entry

    def finalize(self, *, failed: bool = False, error: str | None = None) -> ArtifactManifest:
        now = _utc_now()
        for entry in self.manifest.artifacts:
            if entry.status in {"pending", "staging"}:
                entry.status = "failed"
                entry.error = entry.error or "Run ended before the file became stable."
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
