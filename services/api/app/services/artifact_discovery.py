import base64
import csv
import hashlib
from datetime import datetime
from pathlib import Path

from app import schemas
from app.schemas.artifact import ArtifactType
from app.services import mock_store


SUPPORTED_SUFFIXES = {".md", ".pptx", ".png", ".jpg", ".jpeg", ".csv", ".xlsx"}
IGNORED_PARTS = {".git", ".next", ".venv", "__pycache__", "node_modules"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _candidate_roots() -> list[Path]:
    repo_root = _repo_root()
    return [
        repo_root / "services" / "api" / "deep-research-reports",
        repo_root / "artifacts",
        repo_root / "outputs",
        Path.home() / "ppt_decks",
    ]


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_PARTS for part in path.parts)


def _artifact_id(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"artifact_{digest}"


def _artifact_type(path: Path) -> ArtifactType:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "markdown_report"
    if suffix == ".pptx":
        return "ppt_deck"
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "image_result"
    if suffix in {".csv", ".xlsx"}:
        return "data_table"
    return "markdown_report"


def _read_text(path: Path, max_chars: int = 300_000) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError:
        return None


def _csv_metadata(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file)
            rows = list(reader)
    except OSError:
        return {}

    if not rows:
        return {}

    return {
        "columns": rows[0],
        "rows": rows[1:101],
        "summary": [
            {"label": "Rows", "value": str(max(len(rows) - 1, 0))},
            {"label": "Columns", "value": str(len(rows[0]))},
        ],
    }


def _image_metadata(path: Path) -> dict:
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        encoded = ""

    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return {
        "images": [
            {
                "id": _artifact_id(path),
                "prompt": path.stem,
                "url": f"data:{mime};base64,{encoded}" if encoded else None,
            }
        ]
    }


def _metadata(path: Path, artifact_type: ArtifactType) -> dict:
    base = {
        "filename": path.name,
        "path": str(path),
        "size": path.stat().st_size,
        "updatedAt": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
    }

    if artifact_type == "data_table" and path.suffix.lower() == ".csv":
        base.update(_csv_metadata(path))
    elif artifact_type == "image_result":
        base.update(_image_metadata(path))

    return base


def _content(path: Path, artifact_type: ArtifactType) -> str | None:
    if artifact_type == "markdown_report":
        return _read_text(path)
    return None


def _existing_artifact_keys() -> tuple[set[str], set[str]]:
    existing_paths = {
        str((artifact.metadata or {}).get("path"))
        for artifact in mock_store.artifacts
        if artifact.metadata
    }
    existing_ids = {artifact.id for artifact in mock_store.artifacts}
    return existing_paths, existing_ids


def _artifact_from_path(session_id: str, path: Path) -> schemas.Artifact | None:
    if not path.exists() or not path.is_file() or _is_ignored(path):
        return None
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return None

    artifact_type = _artifact_type(path)
    return schemas.Artifact(
        id=_artifact_id(path),
        session_id=session_id,
        type=artifact_type,
        title=path.stem,
        status="ready",
        content=_content(path, artifact_type),
        metadata=_metadata(path, artifact_type),
    )


def create_artifacts_from_paths(
    session_id: str,
    paths: list[str],
) -> list[schemas.Artifact]:
    existing_paths, existing_ids = _existing_artifact_keys()
    artifacts: list[schemas.Artifact] = []

    for raw_path in paths:
        path = Path(raw_path)
        artifact = _artifact_from_path(session_id, path)
        if artifact is None:
            continue
        if artifact.id in existing_ids or str(path) in existing_paths:
            continue

        artifacts.append(artifact)
        existing_ids.add(artifact.id)
        existing_paths.add(str(path))

    artifacts.sort(
        key=lambda artifact: str((artifact.metadata or {}).get("updatedAt", "")),
        reverse=True,
    )
    return artifacts


def discover_artifacts_since(session_id: str, since: datetime) -> list[schemas.Artifact]:
    existing_paths, existing_ids = _existing_artifact_keys()
    discovered: list[schemas.Artifact] = []

    for root in _candidate_roots():
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file() or _is_ignored(path):
                continue
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue

            try:
                updated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=since.tzinfo)
            except OSError:
                continue

            if updated_at < since:
                continue
            if str(path) in existing_paths:
                continue

            artifact = _artifact_from_path(session_id, path)
            if artifact is None:
                continue
            if artifact.id in existing_ids:
                continue
            discovered.append(artifact)
            existing_ids.add(artifact.id)
            existing_paths.add(str(path))

    discovered.sort(
        key=lambda artifact: str((artifact.metadata or {}).get("updatedAt", "")),
        reverse=True,
    )
    return discovered
