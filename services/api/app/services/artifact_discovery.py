import base64
import csv
import hashlib
import json
import os
import re
import shutil
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from app import schemas
from app.core.config import settings
from app.schemas.artifact import ArtifactType
from app.services import mock_store


SUPPORTED_SUFFIXES = {".md", ".html", ".htm", ".pptx", ".png", ".jpg", ".jpeg", ".csv", ".xlsx"}
IGNORED_PARTS = {".git", ".next", ".venv", "__pycache__", "node_modules"}
IGNORED_FILENAMES = {"request.md"}
OUTPUT_PATH_MARKERS = {
    "/deep-research-reports/",
    "/reports/",
    "/outputs/",
    "/artifacts/",
    "/images/",
    "/ppt_decks/",
    "\\deep-research-reports\\",
    "\\reports\\",
    "\\outputs\\",
    "\\artifacts\\",
    "\\images\\",
    "\\ppt_decks\\",
}
NON_ARTIFACT_MARKERS = {
    "/.hermes/skills/",
    "\\.hermes\\skills\\",
    "/node_modules/",
    "\\node_modules\\",
}
ARTIFACT_PATH_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:\\|/mnt/[a-zA-Z]/|/home/|/tmp/)[^\"'<>|`\r\n]+?\.(?:md|html?|pptx|png|jpe?g|csv|xlsx))",
    re.IGNORECASE,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _candidate_roots() -> list[Path]:
    repo_root = _repo_root()
    user_home = Path.home()
    roots = [
        repo_root / "services" / "api" / "deep-research-reports",
        repo_root / "artifacts",
        repo_root / "outputs",
        user_home / "Desktop",
        user_home / "Documents" / "WebAgent",
        user_home / "Documents" / "deep-research-reports",
        user_home / "Downloads" / "WebAgent",
        user_home / "deep-research-reports",
        user_home / "ppt_decks",
        user_home / ".hermes" / "images",
        Path(r"\\wsl.localhost\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\reports"),
        Path(r"\\wsl.localhost\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\images"),
        Path(r"\\wsl$\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\reports"),
        Path(r"\\wsl$\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\images"),
        Path(
            r"\\wsl.localhost\Ubuntu\home\zhuchangbiaozhu_xyl\hermes-aws-ai-agent\deep-research-reports"
        ),
        Path(
            r"\\wsl$\Ubuntu\home\zhuchangbiaozhu_xyl\hermes-aws-ai-agent\deep-research-reports"
        ),
    ]
    deduped: list[Path] = []
    seen_suffixes: set[str] = set()
    for root in roots:
        suffix = str(root).replace("\\\\wsl$\\Ubuntu", "").replace(
            "\\\\wsl.localhost\\Ubuntu", ""
        )
        if suffix in seen_suffixes:
            continue
        if root.exists():
            seen_suffixes.add(suffix)
        deduped.append(root)
    return deduped


def _hermes_session_roots() -> list[Path]:
    return [
        Path(r"\\wsl.localhost\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\sessions"),
        Path(r"\\wsl$\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\sessions"),
    ]


def _runtime_artifacts_dir(run_id: str | None) -> Path:
    repo_root = _repo_root()
    run_part = run_id or "unbound"
    path = repo_root / "runtime" / "hermes-runs" / run_part / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _runtime_run_dir(run_id: str | None) -> Path:
    return _runtime_artifacts_dir(run_id).parent


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_PARTS for part in path.parts)


def _is_likely_output_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    if any(marker.replace("\\", "/") in normalized for marker in NON_ARTIFACT_MARKERS):
        return False
    return any(marker.replace("\\", "/") in normalized for marker in OUTPUT_PATH_MARKERS)


def _artifact_id(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"artifact_{digest}"


def _file_sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _normalized_path_key(path: str | Path) -> str:
    value = str(path).strip().strip(".,;:)]}\"'").replace("\\", "/")
    lower_value = value.lower()
    if lower_value.startswith("//wsl.localhost/ubuntu/"):
        return "/" + value.split("/Ubuntu/", maxsplit=1)[1].lower()
    if lower_value.startswith("//wsl$/ubuntu/"):
        return "/" + value.split("/Ubuntu/", maxsplit=1)[1].lower()
    match = re.match(r"^([a-zA-Z]):/(.*)$", value)
    if match:
        return f"/mnt/{match.group(1).lower()}/{match.group(2).lower()}"
    return lower_value


def _artifact_type(path: Path) -> ArtifactType:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "markdown_report"
    if suffix in {".html", ".htm"}:
        return "html_page"
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


def _metadata(
    path: Path,
    artifact_type: ArtifactType,
    *,
    original_path: str | None = None,
) -> dict:
    base = {
        "contentHash": _file_sha256(path),
        "filename": path.name,
        "normalizedPath": _normalized_path_key(path),
        "path": str(path),
        "size": path.stat().st_size,
        "updatedAt": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
    }
    if original_path and original_path != str(path):
        base["originalPath"] = original_path
        base["originalNormalizedPath"] = _normalized_path_key(original_path)

    if artifact_type == "data_table" and path.suffix.lower() == ".csv":
        base.update(_csv_metadata(path))
    elif artifact_type == "image_result":
        base.update(_image_metadata(path))

    return base


def _content(path: Path, artifact_type: ArtifactType) -> str | None:
    if artifact_type in {"markdown_report", "html_page"}:
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


def _artifact_from_path(
    session_id: str,
    path: Path,
    *,
    original_path: str | None = None,
) -> schemas.Artifact | None:
    if not path.exists() or not path.is_file() or _is_ignored(path):
        return None
    if path.name.lower() in IGNORED_FILENAMES:
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
        metadata=_metadata(path, artifact_type, original_path=original_path),
    )


def _normalize_path(raw_path: str) -> Path:
    match = raw_path.strip().strip(".,;:)]}\"'").replace("\\", "/")
    if match.startswith("/mnt/") and len(match) > 6 and match[6] == "/":
        drive = match[5].upper()
        rest = match[7:].replace("/", "\\")
        return Path(f"{drive}:\\{rest}")
    if match.startswith("/home/"):
        return Path(r"\\wsl.localhost\Ubuntu") / match.lstrip("/").replace("/", "\\")
    return Path(raw_path.strip().strip(".,;:)]}\"'"))


def _archive_artifact_path(path: Path, run_id: str | None) -> Path:
    if not run_id:
        return path
    if not path.exists() or not path.is_file():
        return path

    artifact_dir = _runtime_artifacts_dir(run_id)
    digest = hashlib.sha1(str(path).encode("utf-8", errors="ignore")).hexdigest()[:10]
    destination = artifact_dir / f"{path.stem}-{digest}{path.suffix.lower()}"
    if not destination.exists() or destination.stat().st_mtime < path.stat().st_mtime:
        shutil.copy2(path, destination)
    return destination


def _path_to_wsl(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix().split(":", 1)[1].lstrip("/")
    return f"/mnt/{drive}/{rest}" if drive else resolved.as_posix()


def _run_pptx_export(
    deck_dir: Path,
    output_dir: Path,
    output_filename: str,
    timeout_seconds: int,
) -> Path | None:
    script_path = f"{settings.hermes_home.rstrip('/')}/skills/sn-ppt-standard/scripts/export_pptx/html_to_pptx.mjs"
    if os.name == "nt":
        command = (
            f"node {shlex.quote(script_path)} "
            f"--deck-dir {shlex.quote(_path_to_wsl(deck_dir))} "
            f"--output {shlex.quote(output_filename)} "
            f"--output-dir {shlex.quote(_path_to_wsl(output_dir))} "
            "--force"
        )
        result = subprocess.run(
            [
                "wsl",
                "-d",
                settings.hermes_wsl_distribution,
                "--",
                "bash",
                "-lc",
                command,
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    else:
        result = subprocess.run(
            [
                "node",
                script_path,
                "--deck-dir",
                str(deck_dir),
                "--output",
                output_filename,
                "--output-dir",
                str(output_dir),
                "--force",
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

    if result.returncode != 0:
        return None

    output_path = output_dir / output_filename
    return output_path if output_path.exists() and output_path.stat().st_size > 0 else None


def _extract_path_strings(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, str):
        for match in ARTIFACT_PATH_RE.finditer(value):
            paths.append(match.group("path"))
        return paths
    if isinstance(value, dict):
        for item in value.values():
            paths.extend(_extract_path_strings(item))
        return paths
    if isinstance(value, list):
        for item in value:
            paths.extend(_extract_path_strings(item))
    return paths


def _as_local_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)


def discover_artifact_paths_from_hermes_sessions(since: datetime) -> list[str]:
    since = _as_local_naive(since)
    paths: list[str] = []
    seen: set[str] = set()

    for root in _hermes_session_roots():
        if not root.exists():
            continue
        for session_file in root.glob("session_*.json"):
            try:
                updated_at = datetime.fromtimestamp(session_file.stat().st_mtime)
            except OSError:
                continue
            if updated_at < since:
                continue
            try:
                data = json.loads(session_file.read_text(encoding="utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            for raw_path in _extract_path_strings(data):
                normalized_path = _normalize_path(raw_path)
                normalized = str(normalized_path)
                if not _is_likely_output_path(raw_path) and not _is_likely_output_path(normalized):
                    continue
                if normalized_path.name.lower() in IGNORED_FILENAMES:
                    continue
                try:
                    file_updated_at = datetime.fromtimestamp(normalized_path.stat().st_mtime)
                except OSError:
                    continue
                if file_updated_at < since:
                    continue
                if normalized in seen:
                    continue
                seen.add(normalized)
                paths.append(raw_path)

    return paths


def create_artifacts_from_paths(
    session_id: str,
    paths: list[str],
    run_id: str | None = None,
) -> list[schemas.Artifact]:
    existing_paths, existing_ids = _existing_artifact_keys()
    existing_hashes: set[str] = set()
    artifacts: list[schemas.Artifact] = []

    for raw_path in paths:
        path = _normalize_path(raw_path)
        archived_path = _archive_artifact_path(path, run_id)
        artifact = _artifact_from_path(
            session_id,
            archived_path,
            original_path=str(path),
        )
        if artifact is None:
            continue
        metadata = artifact.metadata or {}
        content_hash = str(metadata.get("contentHash") or "")
        normalized_path = str(metadata.get("originalNormalizedPath") or metadata.get("normalizedPath") or "")
        if (
            artifact.id in existing_ids
            or str(path) in existing_paths
            or (normalized_path and normalized_path in existing_paths)
            or (content_hash and content_hash in existing_hashes)
        ):
            continue

        artifacts.append(artifact)
        existing_ids.add(artifact.id)
        existing_paths.add(str(path))
        if normalized_path:
            existing_paths.add(normalized_path)
        if content_hash:
            existing_hashes.add(content_hash)

    artifacts.sort(
        key=lambda artifact: str((artifact.metadata or {}).get("updatedAt", "")),
        reverse=True,
    )
    return artifacts


def create_pptx_from_html_artifacts(
    session_id: str,
    html_artifacts: list[schemas.Artifact],
    run_id: str | None,
    timeout_seconds: int | None = None,
) -> schemas.Artifact | None:
    html_paths: list[Path] = []
    for artifact in html_artifacts:
        if artifact.type != "html_page":
            continue
        metadata = artifact.metadata or {}
        raw_path = str(metadata.get("path") or metadata.get("originalPath") or "")
        if not raw_path:
            continue
        path = Path(raw_path)
        if path.exists() and path.is_file():
            html_paths.append(path)

    if not html_paths:
        return None

    def sort_key(path: Path) -> tuple[int, str]:
        match = re.search(r"page[_-]?(\d+)", path.stem, re.IGNORECASE)
        return (int(match.group(1)) if match else 9999, path.name)

    html_paths = sorted(html_paths, key=sort_key)
    run_dir = _runtime_run_dir(run_id)
    deck_dir = run_dir / "pptx-fallback"
    pages_dir = deck_dir / "pages"
    output_dir = _runtime_artifacts_dir(run_id)
    pages_dir.mkdir(parents=True, exist_ok=True)

    for index, source in enumerate(html_paths, start=1):
        shutil.copy2(source, pages_dir / f"page_{index:03d}.html")

    output_filename = "agent-generated-deck.pptx"
    output_path = _run_pptx_export(
        deck_dir,
        output_dir,
        output_filename,
        timeout_seconds or settings.agent_run_ppt_export_timeout_seconds,
    )
    if output_path is None:
        return None

    return _artifact_from_path(
        session_id,
        output_path,
        original_path=str(output_path),
    )


def discover_artifacts_since(
    session_id: str,
    since: datetime,
    run_id: str | None = None,
) -> list[schemas.Artifact]:
    since = _as_local_naive(since)
    existing_paths, existing_ids = _existing_artifact_keys()
    existing_hashes: set[str] = set()
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
                updated_at = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError:
                continue

            if updated_at < since:
                continue
            if str(path) in existing_paths:
                continue

            archived_path = _archive_artifact_path(path, run_id)
            artifact = _artifact_from_path(
                session_id,
                archived_path,
                original_path=str(path),
            )
            if artifact is None:
                continue
            metadata = artifact.metadata or {}
            content_hash = str(metadata.get("contentHash") or "")
            normalized_path = str(metadata.get("originalNormalizedPath") or metadata.get("normalizedPath") or "")
            if (
                artifact.id in existing_ids
                or (normalized_path and normalized_path in existing_paths)
                or (content_hash and content_hash in existing_hashes)
            ):
                continue
            discovered.append(artifact)
            existing_ids.add(artifact.id)
            existing_paths.add(str(path))
            if normalized_path:
                existing_paths.add(normalized_path)
            if content_hash:
                existing_hashes.add(content_hash)

    discovered.sort(
        key=lambda artifact: str((artifact.metadata or {}).get("updatedAt", "")),
        reverse=True,
    )
    return discovered
