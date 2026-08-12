import asyncio
import base64
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app import schemas
from app.schemas.artifact import ArtifactType
from app.services.agent_run_workspace import run_artifacts_dir
from app.services.artifact_dedupe import dedupe_discovered_artifacts

SUPPORTED_SUFFIXES = {
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
IGNORED_PARTS = {".git", ".next", ".venv", "__pycache__", "node_modules"}
IGNORED_FILENAMES = {"request.md"}
OUTPUT_PATH_MARKERS = {
    "/deep-research-reports/",
    "/reports/",
    "/output/",
    "/outputs/",
    "/artifacts/",
    "/images/",
    "/ppt_decks/",
    "\\deep-research-reports\\",
    "\\reports\\",
    "\\output\\",
    "\\outputs\\",
    "\\artifacts\\",
    "\\images\\",
    "\\ppt_decks\\",
}


def explicit_artifact_source_dirs(explicit_artifacts: list[object] | None) -> list[str]:
    source_dirs: list[str] = []
    for artifact_ref in explicit_artifacts or []:
        value = (
            artifact_ref.get("source_dir") or artifact_ref.get("sourceDir")
            if isinstance(artifact_ref, dict)
            else getattr(artifact_ref, "source_dir", None)
        )
        if isinstance(value, str) and value:
            source_dirs.append(value)
    return source_dirs


async def discover_artifacts_with_retry(
    session_id: str,
    since: datetime,
    explicit_artifact_paths: list[str],
    run_id: str | None,
    explicit_artifacts: list[object] | None = None,
) -> list[schemas.Artifact]:
    for attempt in range(5):
        discovered_artifacts = await asyncio.to_thread(
            create_artifacts_from_refs,
            session_id,
            explicit_artifacts or [],
            run_id,
        )
        if not discovered_artifacts:
            discovered_artifacts = await asyncio.to_thread(
                create_artifacts_from_paths,
                session_id,
                explicit_artifact_paths,
                run_id,
            )
        if discovered_artifacts:
            related_paths = await asyncio.to_thread(
                discover_related_artifact_paths,
                explicit_artifact_paths,
                since,
                source_dirs=explicit_artifact_source_dirs(explicit_artifacts),
            )
            if related_paths:
                discovered_artifacts.extend(
                    await asyncio.to_thread(
                        create_artifacts_from_paths,
                        session_id,
                        related_paths,
                        run_id,
                    )
                )
                discovered_artifacts = dedupe_discovered_artifacts(discovered_artifacts)
        if not discovered_artifacts:
            session_artifact_paths = await asyncio.to_thread(
                discover_artifact_paths_from_hermes_sessions,
                since,
            )
            discovered_artifacts = await asyncio.to_thread(
                create_artifacts_from_paths,
                session_id,
                session_artifact_paths,
                run_id,
            )
        if not discovered_artifacts and run_id is None:
            discovered_artifacts = await asyncio.to_thread(
                discover_artifacts_since,
                session_id,
                since,
                run_id,
            )
        if discovered_artifacts or attempt == 4:
            return dedupe_discovered_artifacts(discovered_artifacts)
        await asyncio.sleep(2)
    return []


NON_ARTIFACT_MARKERS = {
    "/.hermes/skills/",
    "\\.hermes\\skills\\",
    "/node_modules/",
    "\\node_modules\\",
}
ARTIFACT_PATH_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:\\|/mnt/[^/]+/|/home/|/tmp/|(?:\.?/)?(?:output|outputs|artifacts|ppt_decks|deep-research-reports)/)[^\"'<>|`\r\n]+?\.(?:md|html?|pptx|png|jpe?g|csv|xlsx|json))",
    re.IGNORECASE,
)
ARTIFACT_FILENAME_RE = re.compile(
    r"(?<![\w./\\-])"
    r"(?P<path>(?:\./)?[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,180}"
    r"\.(?:md|html?|pptx|png|jpe?g|csv|xlsx|json))(?=$|[\s`'\"*),.;:])",
    re.IGNORECASE,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _candidate_roots() -> list[Path]:
    repo_root = _repo_root()
    user_home = Path.home()
    roots = [
        repo_root / "deep-research-reports",
        # Hermes can write a relative final filename from the API process cwd.
        # Keep this root explicit so a completion line such as "report.md"
        # is resolved before the broader fallback scans run.
        repo_root / "services" / "api",
        repo_root / "services" / "api" / "deep-research-reports",
        repo_root / "ppt_decks",
        repo_root / "artifacts",
        repo_root / "output",
        repo_root / "outputs",
        repo_root / ".hermes" / "plans",
        user_home / "Desktop",
        user_home / "Documents" / "WebAgent",
        user_home / "Documents" / "deep-research-reports",
        user_home / "Downloads" / "WebAgent",
        user_home / "deep-research-reports",
        user_home / "ppt_decks",
        user_home / ".hermes" / "images",
        user_home / ".hermes" / "deep-research-reports",
        Path(r"\\wsl.localhost\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\reports"),
        Path(r"\\wsl.localhost\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\deep-research-reports"),
        Path(r"\\wsl.localhost\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\images"),
        Path(r"\\wsl$\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\reports"),
        Path(r"\\wsl$\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\deep-research-reports"),
        Path(r"\\wsl$\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\images"),
        Path(
            r"\\wsl.localhost\Ubuntu\home\zhuchangbiaozhu_xyl\hermes-aws-ai-agent\deep-research-reports"
        ),
        Path(r"\\wsl$\Ubuntu\home\zhuchangbiaozhu_xyl\hermes-aws-ai-agent\deep-research-reports"),
    ]
    deduped: list[Path] = []
    seen_suffixes: set[str] = set()
    for root in roots:
        suffix = str(root).replace("\\\\wsl$\\Ubuntu", "").replace("\\\\wsl.localhost\\Ubuntu", "")
        if suffix in seen_suffixes:
            continue
        if root.exists():
            seen_suffixes.add(suffix)
        deduped.append(root)
    return deduped


def _resolve_bare_artifact_filename(filename: str) -> Path | None:
    name = Path(filename).name
    if not name or Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
        return None

    candidates: list[Path] = []
    for root in _candidate_roots():
        if not root.exists() or not root.is_dir():
            continue
        direct_candidate = root / name
        if _is_regular_artifact_candidate(direct_candidate):
            candidates.append(direct_candidate)
        try:
            for candidate in root.rglob(name):
                if _is_regular_artifact_candidate(candidate):
                    candidates.append(candidate)
        except OSError:
            continue

    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _hermes_session_roots() -> list[Path]:
    return [
        Path(r"\\wsl.localhost\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\sessions"),
        Path(r"\\wsl$\Ubuntu\home\zhuchangbiaozhu_xyl\.hermes\sessions"),
    ]


def _runtime_artifacts_dir(run_id: str | None) -> Path:
    if run_id:
        return run_artifacts_dir(run_id)
    path = _repo_root() / "runtime" / "agent-runs" / "unbound" / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _runtime_run_dir(run_id: str | None) -> Path:
    return _runtime_artifacts_dir(run_id).parent


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_PARTS for part in path.parts)


def _is_regular_artifact_candidate(path: Path) -> bool:
    try:
        if path.is_file() and not _is_ignored(path):
            return True
    except OSError:
        pass
    return _wsl_artifact_mtime(path) is not None and not _is_ignored(path)


def _windows_path_to_wsl(path: Path) -> str | None:
    if os.name != "nt":
        return None
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", str(path))
    if not match:
        return None
    relative_path = match.group(2).replace("\\", "/")
    return f"/mnt/{match.group(1).lower()}/{relative_path}"


def _wsl_artifact_mtime(path: Path) -> float | None:
    """Read WSL-backed files when Windows cannot stat a newly-created binary."""
    wsl_path = _windows_path_to_wsl(path)
    if not wsl_path or shutil.which("wsl.exe") is None:
        return None
    try:
        result = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu", "--", "stat", "-c", "%F:%Y", wsl_path],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    file_type, separator, timestamp = result.stdout.strip().partition(":")
    if file_type != "regular file" or not separator:
        return None
    try:
        return float(timestamp)
    except ValueError:
        return None


def _artifact_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return _wsl_artifact_mtime(path)


def _materialize_wsl_artifact(path: Path) -> tuple[Path, Path | None]:
    """Materialize a WSL-only artifact into a temporary Windows-readable file."""
    if path.is_file():
        return path, None
    wsl_path = _windows_path_to_wsl(path)
    if not wsl_path or shutil.which("wsl.exe") is None:
        return path, None

    temp_dir = Path(tempfile.mkdtemp(prefix="webagent-artifact-"))
    temp_path = temp_dir / path.name
    try:
        with temp_path.open("wb") as output:
            result = subprocess.run(
                ["wsl.exe", "-d", "Ubuntu", "--", "cat", wsl_path],
                stdout=output,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )
        if result.returncode != 0 or not temp_path.is_file() or temp_path.stat().st_size == 0:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return path, None
        return temp_path, temp_dir
    except (OSError, subprocess.SubprocessError):
        shutil.rmtree(temp_dir, ignore_errors=True)
        return path, None


def _is_non_artifact_path(path: str | Path) -> bool:
    normalized = str(path).replace("\\", "/").lower()
    return any(marker.replace("\\", "/") in normalized for marker in NON_ARTIFACT_MARKERS)


def _is_repo_runtime_temp_path(path: Path) -> bool:
    try:
        relative_path = path.resolve().relative_to((_repo_root() / "runtime").resolve())
    except ValueError:
        return False

    parts = relative_path.parts
    if len(parts) >= 3 and parts[0] == "hermes-runs":
        return "artifacts" not in parts
    if parts and parts[0] == "users":
        normalized_parts = {part.lower() for part in parts}
        run_output_dirs = {
            "artifacts",
            "deep-research-reports",
            "images",
            "output",
            "outputs",
            "ppt_decks",
            "reports",
        }
        if "runs" in normalized_parts and normalized_parts.intersection(run_output_dirs):
            return False
    return True


def _is_safe_related_artifact_dir(directory: Path) -> bool:
    normalized = str(directory).replace("\\", "/").lower().rstrip("/")
    broad_dirs = {
        str(_repo_root()).replace("\\", "/").lower().rstrip("/"),
        str(Path.home()).replace("\\", "/").lower().rstrip("/"),
    }
    if normalized in broad_dirs:
        return False
    return any(
        marker in normalized
        for marker in (
            "artifacts",
            "deep-research-reports",
            "images",
            "output",
            "outputs",
            "ppt_decks",
            "reports",
        )
    )


def _is_likely_output_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    if _is_non_artifact_path(path):
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
    if suffix == ".json":
        return "debug_json"
    return "markdown_report"


def _artifact_role(path: Path, artifact_type: ArtifactType) -> str:
    normalized = str(path).replace("\\", "/").lower()
    filename = path.name.lower()
    stem = path.stem.lower()
    intermediate_names = {
        "blueprint.json",
        "briefing.json",
        "evidence.json",
        "info_pack.json",
        "outline.json",
        "plan.json",
        "raw_documents.json",
        "task_pack.json",
        "blueprint.md",
        "briefing.md",
        "outline.md",
        "plan.md",
    }
    intermediate_markers = {
        "/source_cache/",
        "/sub_reports/",
        "/sub-reports/",
        "/evidence/",
        "/cache/",
        "/tmp/",
    }

    if artifact_type == "debug_json" or filename in intermediate_names:
        return "intermediate"
    if any(marker in normalized for marker in intermediate_markers):
        return "intermediate"
    if artifact_type == "markdown_report" and stem in {
        "plan",
        "outline",
        "briefing",
        "blueprint",
        "evidence",
    }:
        return "intermediate"
    return "primary"


def _valid_artifact_type(value: object, fallback: ArtifactType) -> ArtifactType:
    supported = set(ArtifactType.__args__)
    return value if isinstance(value, str) and value in supported else fallback


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
    role_path = Path(original_path) if original_path else path
    artifact_role = _artifact_role(role_path, artifact_type)
    normalized_path = str(role_path).replace("\\", "/").lower()
    if (
        artifact_type == "html_page"
        and "/pages/" in normalized_path
        and path.name.lower().startswith("page_")
    ):
        artifact_role = "preview_fallback"
    base = {
        "artifactRole": artifact_role,
        "contentHash": _file_sha256(path),
        "developerOnly": artifact_role == "intermediate",
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
    if artifact_type in {"debug_json", "markdown_report", "html_page"}:
        return _read_text(path)
    return None


def _artifact_from_path(
    session_id: str,
    path: Path,
    *,
    artifact_type_override: str | None = None,
    metadata_extra: dict[str, Any] | None = None,
    original_path: str | None = None,
    title_override: str | None = None,
) -> schemas.Artifact | None:
    if not _is_regular_artifact_candidate(path):
        return None
    if path.name.lower() in IGNORED_FILENAMES:
        return None
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return None

    artifact_type = _valid_artifact_type(artifact_type_override, _artifact_type(path))
    metadata = _metadata(path, artifact_type, original_path=original_path)
    if metadata_extra:
        metadata.update({key: value for key, value in metadata_extra.items() if value is not None})
    return schemas.Artifact(
        id=_artifact_id(path),
        session_id=session_id,
        type=artifact_type,
        title=title_override or path.stem,
        status="ready",
        content=_content(path, artifact_type),
        metadata=metadata,
    )


def _normalize_path(raw_path: str) -> Path:
    match = raw_path.strip().strip(".,;:)]}\"'").replace("\\", "/")
    relative_match = match.lstrip("./")
    if relative_match.startswith(
        (
            "output/",
            "outputs/",
            "artifacts/",
            "ppt_decks/",
            "deep-research-reports/",
        )
    ):
        return _repo_root() / relative_match
    if "/" not in relative_match and Path(relative_match).suffix.lower() in SUPPORTED_SUFFIXES:
        return _resolve_bare_artifact_filename(relative_match) or _repo_root() / relative_match
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
    if not _is_regular_artifact_candidate(path):
        return path

    artifact_dir = _runtime_artifacts_dir(run_id)
    digest = hashlib.sha1(str(path).encode("utf-8", errors="ignore")).hexdigest()[:10]
    destination = artifact_dir / f"{path.stem}-{digest}{path.suffix.lower()}"
    if not destination.exists() or destination.stat().st_mtime < path.stat().st_mtime:
        shutil.copy2(path, destination)
    return destination


def _extract_path_strings(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, str):
        for match in ARTIFACT_PATH_RE.finditer(value):
            paths.append(match.group("path"))
        for match in ARTIFACT_FILENAME_RE.finditer(value):
            filename = match.group("path").strip()
            if filename not in paths:
                paths.append(filename)
        return paths
    if isinstance(value, dict):
        for item in value.values():
            paths.extend(_extract_path_strings(item))
        return paths
    if isinstance(value, list):
        for item in value:
            paths.extend(_extract_path_strings(item))
    return paths


def extract_artifact_path_strings(value: Any) -> list[str]:
    return _extract_path_strings(value)


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
                file_mtime = _artifact_mtime(normalized_path)
                if file_mtime is None:
                    continue
                file_updated_at = datetime.fromtimestamp(file_mtime)
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
    existing_paths: set[str] = set()
    existing_ids: set[str] = set()
    existing_hashes: set[str] = set()
    artifacts: list[schemas.Artifact] = []

    for raw_path in paths:
        path = _normalize_path(raw_path)
        if _is_non_artifact_path(raw_path) or _is_non_artifact_path(path):
            continue
        if _is_repo_runtime_temp_path(path):
            continue
        readable_path, temp_dir = _materialize_wsl_artifact(path)
        try:
            archived_path = _archive_artifact_path(readable_path, run_id)
            artifact = _artifact_from_path(
                session_id,
                archived_path,
                original_path=str(path),
            )
        finally:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)
        if artifact is None:
            continue
        metadata = artifact.metadata or {}
        content_hash = str(metadata.get("contentHash") or "")
        normalized_path = str(
            metadata.get("originalNormalizedPath") or metadata.get("normalizedPath") or ""
        )
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


def create_artifacts_from_refs(
    session_id: str,
    artifact_refs: list[object],
    run_id: str | None = None,
) -> list[schemas.Artifact]:
    existing_paths: set[str] = set()
    existing_ids: set[str] = set()
    existing_hashes: set[str] = set()
    artifacts: list[schemas.Artifact] = []

    for artifact_ref in artifact_refs:
        path_value = getattr(artifact_ref, "path", None)
        if not path_value and isinstance(artifact_ref, dict):
            path_value = (
                artifact_ref.get("path")
                or artifact_ref.get("artifact_path")
                or artifact_ref.get("artifactPath")
            )
        if not isinstance(path_value, str) or not path_value:
            continue

        artifact_type = (
            getattr(artifact_ref, "artifact_type", None)
            if not isinstance(artifact_ref, dict)
            else artifact_ref.get("artifact_type") or artifact_ref.get("artifactType")
        )
        source_dir = (
            getattr(artifact_ref, "source_dir", None)
            if not isinstance(artifact_ref, dict)
            else artifact_ref.get("source_dir") or artifact_ref.get("sourceDir")
        )
        ref_run_id = (
            getattr(artifact_ref, "run_id", None)
            if not isinstance(artifact_ref, dict)
            else artifact_ref.get("run_id") or artifact_ref.get("runId")
        )
        title = (
            getattr(artifact_ref, "title", None)
            if not isinstance(artifact_ref, dict)
            else artifact_ref.get("title")
        )

        path = _normalize_path(path_value)
        if _is_non_artifact_path(path_value) or _is_non_artifact_path(path):
            continue
        if _is_repo_runtime_temp_path(path):
            continue
        readable_path, temp_dir = _materialize_wsl_artifact(path)
        try:
            archived_path = _archive_artifact_path(readable_path, run_id)
            artifact = _artifact_from_path(
                session_id,
                archived_path,
                artifact_type_override=artifact_type,
                metadata_extra={
                    "adapterProtocol": "hermes.artifact.v1",
                    "adapterRunId": ref_run_id,
                    "adapterSourceDir": source_dir,
                    "adapterTitle": title,
                    "adapterType": artifact_type,
                },
                original_path=str(path),
                title_override=title if isinstance(title, str) and title else None,
            )
        finally:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)
        if artifact is None:
            continue

        metadata = artifact.metadata or {}
        content_hash = str(metadata.get("contentHash") or "")
        normalized_path = str(
            metadata.get("originalNormalizedPath") or metadata.get("normalizedPath") or ""
        )
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


def discover_related_artifact_paths(
    paths: list[str],
    since: datetime,
    *,
    source_dirs: list[str] | None = None,
) -> list[str]:
    since = _as_local_naive(since)
    directories: list[Path] = []
    seen_dirs: set[str] = set()

    for raw_path in paths:
        path = _normalize_path(raw_path)
        if _is_non_artifact_path(raw_path) or _is_non_artifact_path(path):
            continue
        parent = path.parent
        if not _is_safe_related_artifact_dir(parent):
            continue
        key = _normalized_path_key(parent)
        if key not in seen_dirs:
            seen_dirs.add(key)
            directories.append(parent)

    for raw_dir in source_dirs or []:
        directory = _normalize_path(raw_dir)
        if _is_non_artifact_path(raw_dir) or _is_non_artifact_path(directory):
            continue
        if not _is_safe_related_artifact_dir(directory):
            continue
        key = _normalized_path_key(directory)
        if key not in seen_dirs:
            seen_dirs.add(key)
            directories.append(directory)

    related_paths: list[str] = []
    seen_paths: set[str] = set()
    for directory in directories:
        if not directory.exists() or not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if _is_repo_runtime_temp_path(path):
                continue
            if path.name.lower() in IGNORED_FILENAMES:
                continue
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if not _is_regular_artifact_candidate(path):
                continue
            file_mtime = _artifact_mtime(path)
            if file_mtime is None:
                continue
            updated_at = datetime.fromtimestamp(file_mtime)
            if updated_at < since:
                continue
            key = _normalized_path_key(path)
            if key in seen_paths:
                continue
            seen_paths.add(key)
            related_paths.append(str(path))

    return related_paths


def discover_artifacts_since(
    session_id: str,
    since: datetime,
    run_id: str | None = None,
) -> list[schemas.Artifact]:
    since = _as_local_naive(since)
    existing_paths: set[str] = set()
    existing_ids: set[str] = set()
    existing_hashes: set[str] = set()
    discovered: list[schemas.Artifact] = []

    for root in _candidate_roots():
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if _is_repo_runtime_temp_path(path):
                continue
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if not _is_regular_artifact_candidate(path):
                continue
            file_mtime = _artifact_mtime(path)
            if file_mtime is None:
                continue
            updated_at = datetime.fromtimestamp(file_mtime)

            if updated_at < since:
                continue
            if str(path) in existing_paths:
                continue

            readable_path, temp_dir = _materialize_wsl_artifact(path)
            try:
                archived_path = _archive_artifact_path(readable_path, run_id)
                artifact = _artifact_from_path(
                    session_id,
                    archived_path,
                    original_path=str(path),
                )
            finally:
                if temp_dir is not None:
                    shutil.rmtree(temp_dir, ignore_errors=True)
            if artifact is None:
                continue
            metadata = artifact.metadata or {}
            content_hash = str(metadata.get("contentHash") or "")
            normalized_path = str(
                metadata.get("originalNormalizedPath") or metadata.get("normalizedPath") or ""
            )
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
