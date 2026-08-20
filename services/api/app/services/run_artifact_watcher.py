# File purpose: Watches one isolated Agent Run workspace and emits stable file transitions.
# Main declarations: ArtifactFileTransition describes a state change; RunArtifactWatcher polls
# output files without treating staged conversation context as new artifacts.

from __future__ import annotations

import asyncio
import os
import stat as stat_module
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.services.artifact_manifest import ARTIFACT_MANIFEST_FILENAME

WATCHED_ARTIFACT_SUFFIXES = {
    ".csv",
    ".htm",
    ".html",
    ".jpeg",
    ".jpg",
    ".json",
    ".md",
    ".png",
    ".pptx",
    ".xlsx",
}
IGNORED_FILENAMES = {ARTIFACT_MANIFEST_FILENAME, "package.json", "request.md"}
IGNORED_SUFFIXES = {".part", ".swp", ".tmp"}
IGNORED_DIRECTORY_NAMES = {
    ".cache",
    ".git",
    ".next",
    ".next-build",
    ".venv",
    "__pycache__",
    "context",
    "node_modules",
    "venv",
}


@dataclass(frozen=True)
class ArtifactFileTransition:
    path: Path
    status: str
    size_bytes: int | None = None
    mtime_ns: int | None = None
    stable_at: datetime | None = None
    error: str | None = None


@dataclass
class _ObservedFile:
    size_bytes: int
    mtime_ns: int
    unchanged_samples: int
    unchanged_since: float
    status: str
    validation_error: str | None = None


class RunArtifactWatcher:
    """Polls one Run workspace and recognizes only durable output files."""

    def __init__(
        self,
        root: Path,
        *,
        poll_interval_seconds: float = 0.5,
        stable_seconds: float = 1.5,
        stable_samples: int = 3,
        ignore_existing: bool = True,
    ) -> None:
        self.root = root.expanduser().resolve()
        self.poll_interval_seconds = max(0.01, poll_interval_seconds)
        self.stable_seconds = max(self.poll_interval_seconds, stable_seconds)
        self.stable_samples = max(2, stable_samples)
        self._observed: dict[Path, _ObservedFile] = {}
        self._existing_signatures: dict[Path, tuple[int, int]] = {}
        if ignore_existing:
            for path, file_stat in self._candidate_files():
                self._existing_signatures[path] = (file_stat.st_size, file_stat.st_mtime_ns)

    def _candidate_files(self) -> list[tuple[Path, os.stat_result]]:
        if not self.root.exists():
            return []
        candidates: list[tuple[Path, os.stat_result]] = []
        for directory, directory_names, filenames in os.walk(
            self.root,
            topdown=True,
            followlinks=False,
        ):
            directory_names[:] = sorted(
                name
                for name in directory_names
                if name.lower() not in IGNORED_DIRECTORY_NAMES
            )
            for filename in sorted(filenames):
                lower_name = filename.lower()
                path = Path(directory) / filename
                if (
                    lower_name in IGNORED_FILENAMES
                    or path.suffix.lower() not in WATCHED_ARTIFACT_SUFFIXES
                    or any(lower_name.endswith(suffix) for suffix in IGNORED_SUFFIXES)
                ):
                    continue
                try:
                    file_stat = path.stat()
                except OSError:
                    continue
                if stat_module.S_ISREG(file_stat.st_mode):
                    candidates.append((path.resolve(), file_stat))
        return sorted(candidates, key=lambda item: str(item[0]))

    @staticmethod
    def _validation_error(path: Path, size_bytes: int) -> str | None:
        if size_bytes <= 0:
            return "Artifact file is empty."
        if path.suffix.lower() in {".pptx", ".xlsx"} and not zipfile.is_zipfile(path):
            return "Office artifact is not a complete ZIP container yet."
        try:
            with path.open("rb") as file:
                file.read(1)
        except OSError as error:
            return f"Artifact file is not readable: {error}"
        return None

    def poll(self) -> list[ArtifactFileTransition]:
        loop_time = asyncio.get_running_loop().time()
        transitions: list[ArtifactFileTransition] = []
        current_paths: set[Path] = set()

        for path, file_stat in self._candidate_files():
            current_paths.add(path)
            existing_signature = self._existing_signatures.get(path)
            if existing_signature == (file_stat.st_size, file_stat.st_mtime_ns):
                continue
            self._existing_signatures.pop(path, None)

            observed = self._observed.get(path)
            if observed is None:
                self._observed[path] = _ObservedFile(
                    size_bytes=file_stat.st_size,
                    mtime_ns=file_stat.st_mtime_ns,
                    unchanged_samples=1,
                    unchanged_since=loop_time,
                    status="pending",
                )
                transitions.append(
                    ArtifactFileTransition(
                        path=path,
                        status="pending",
                        size_bytes=file_stat.st_size,
                        mtime_ns=file_stat.st_mtime_ns,
                    )
                )
                continue

            changed = (
                observed.size_bytes != file_stat.st_size
                or observed.mtime_ns != file_stat.st_mtime_ns
            )
            if changed:
                observed.size_bytes = file_stat.st_size
                observed.mtime_ns = file_stat.st_mtime_ns
                observed.unchanged_samples = 1
                observed.unchanged_since = loop_time
                observed.validation_error = None
                if observed.status != "staging":
                    observed.status = "staging"
                    transitions.append(
                        ArtifactFileTransition(
                            path=path,
                            status="staging",
                            size_bytes=file_stat.st_size,
                            mtime_ns=file_stat.st_mtime_ns,
                        )
                    )
                continue

            observed.unchanged_samples += 1
            stable_for = loop_time - observed.unchanged_since
            if (
                observed.status != "ready"
                and observed.unchanged_samples >= self.stable_samples
                and stable_for >= self.stable_seconds
            ):
                validation_error = self._validation_error(path, file_stat.st_size)
                if validation_error:
                    observed.validation_error = validation_error
                    if observed.status != "staging":
                        observed.status = "staging"
                        transitions.append(
                            ArtifactFileTransition(
                                path=path,
                                status="staging",
                                size_bytes=file_stat.st_size,
                                mtime_ns=file_stat.st_mtime_ns,
                                error=validation_error,
                            )
                        )
                    continue
                observed.status = "ready"
                observed.validation_error = None
                transitions.append(
                    ArtifactFileTransition(
                        path=path,
                        status="ready",
                        size_bytes=file_stat.st_size,
                        mtime_ns=file_stat.st_mtime_ns,
                        stable_at=datetime.now(UTC),
                    )
                )

        for path, observed in list(self._observed.items()):
            if path in current_paths or observed.status == "failed":
                continue
            observed.status = "failed"
            transitions.append(
                ArtifactFileTransition(
                    path=path,
                    status="failed",
                    size_bytes=observed.size_bytes,
                    mtime_ns=observed.mtime_ns,
                    error="File disappeared before it became a durable artifact.",
                )
            )

        return transitions

    def track(self, path: Path) -> None:
        """Treat an explicitly reported in-root path as a candidate for this Run."""

        resolved_path = path.expanduser().resolve()
        try:
            resolved_path.relative_to(self.root)
        except ValueError:
            return
        self._existing_signatures.pop(path, None)
        self._existing_signatures.pop(resolved_path, None)

    async def settle(self, timeout_seconds: float) -> list[ArtifactFileTransition]:
        """Wait briefly for outstanding files and fail anything still being written."""

        deadline = asyncio.get_running_loop().time() + max(0.0, timeout_seconds)
        transitions: list[ArtifactFileTransition] = []
        while asyncio.get_running_loop().time() < deadline:
            transitions.extend(self.poll())
            if not self.has_unsettled_files:
                return transitions
            await asyncio.sleep(self.poll_interval_seconds)

        transitions.extend(self.poll())
        for path, observed in self._observed.items():
            if observed.status in {"ready", "failed"}:
                continue
            observed.status = "failed"
            transitions.append(
                ArtifactFileTransition(
                    path=path,
                    status="failed",
                    size_bytes=observed.size_bytes,
                    mtime_ns=observed.mtime_ns,
                    error=(
                        observed.validation_error
                        or "File did not become stable before the artifact staging timeout."
                    ),
                )
            )
        return transitions

    @property
    def has_unsettled_files(self) -> bool:
        return any(item.status not in {"ready", "failed"} for item in self._observed.values())

    @property
    def failed_paths(self) -> set[Path]:
        return {path.resolve() for path, item in self._observed.items() if item.status == "failed"}


__all__ = ["ArtifactFileTransition", "RunArtifactWatcher", "WATCHED_ARTIFACT_SUFFIXES"]
