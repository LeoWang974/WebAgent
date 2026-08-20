# File purpose: Implements the artifact discovery backend service workflow.
# Main declarations: explicit_artifact_source_dirs handles explicit artifact source dirs;
# discover_artifacts_with_retry discovers artifacts with retry; _repo_root handles repo root;
# _configured_hermes_home_candidates handles configured hermes home candidates; _candidate_roots
# handles candidate roots; _resolve_bare_artifact_filename handles resolve bare artifact filename;
# _hermes_session_roots handles hermes session roots; _runtime_artifacts_dir handles runtime
# artifacts dir; _is_ignored handles is ignored; _is_regular_artifact_candidate handles is regular
# artifact candidate; _windows_path_to_wsl handles windows path to wsl; _wsl_artifact_mtime
# handles wsl artifact mtime; _artifact_mtime handles artifact mtime; _materialize_wsl_artifact
# handles materialize wsl artifact; _is_non_artifact_path handles is non artifact path;
# _is_repo_runtime_temp_path handles is repo runtime temp path; _is_safe_related_artifact_dir
# handles is safe related artifact dir; _is_likely_output_path handles is likely output path;
# _artifact_id handles artifact id; _file_sha256 handles file sha256; _normalized_path_key handles
# normalized path key; _artifact_type handles artifact type; _artifact_role handles artifact role;
# _valid_artifact_type handles valid artifact type; _read_text handles read text; _csv_metadata
# handles csv metadata; _image_metadata handles image metadata; _metadata handles metadata;
# _content handles content; _artifact_from_path handles artifact from path; _normalize_path
# handles normalize path; _archive_artifact_path handles archive artifact path;
# _extract_path_strings handles extract path strings; extract_artifact_path_strings handles
# extract artifact path strings; _as_local_naive handles as local naive;
# discover_artifact_paths_from_hermes_sessions discovers artifact paths from hermes sessions;
# create_artifacts_from_paths creates artifacts from paths; create_artifacts_from_refs creates
# artifacts from refs; discover_related_artifact_paths discovers related artifact paths;
# discover_artifacts_since discovers artifacts since.

import asyncio
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
from app.core.config import settings
from app.schemas.artifact import ArtifactType
from app.schemas.artifact_manifest import SUPPORTED_ARTIFACT_MANIFEST_SCHEMAS
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
IGNORED_PARTS = {
    ".git",
    ".next",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "site-packages",
}
IGNORED_PART_SUFFIXES = (".dist-info", ".egg-info")
IGNORED_FILENAMES = {
    "artifact-manifest.json",
    "package-lock.json",
    "package.json",
    "readme.md",
    "request.md",
    "soul.md",
    "testing.md",
}
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
    *,
    archive_dir: Path | None = None,
    authoritative_manifest: bool = False,
) -> list[schemas.Artifact]:
    attempt_count = 3 if authoritative_manifest else 5
    for attempt in range(attempt_count):
        discovered_artifacts = await asyncio.to_thread(
            create_artifacts_from_refs,
            session_id,
            explicit_artifacts or [],
            run_id,
            archive_dir=archive_dir,
        )
        if not discovered_artifacts:
            discovered_artifacts = await asyncio.to_thread(
                create_artifacts_from_paths,
                session_id,
                explicit_artifact_paths,
                run_id,
                archive_dir=archive_dir,
            )
        if discovered_artifacts and not authoritative_manifest:
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
                        archive_dir=archive_dir,
                    )
                )
                discovered_artifacts = dedupe_discovered_artifacts(discovered_artifacts)
        if not discovered_artifacts and not authoritative_manifest:
            session_artifact_paths = await asyncio.to_thread(
                discover_artifact_paths_from_hermes_sessions,
                since,
            )
            discovered_artifacts = await asyncio.to_thread(
                create_artifacts_from_paths,
                session_id,
                session_artifact_paths,
                run_id,
                archive_dir=archive_dir,
            )
        if not discovered_artifacts and run_id is None:
            discovered_artifacts = await asyncio.to_thread(
                discover_artifacts_since,
                session_id,
                since,
                run_id,
            )
        if discovered_artifacts or attempt == attempt_count - 1:
            return dedupe_discovered_artifacts(discovered_artifacts)
        await asyncio.sleep(0.5 if authoritative_manifest else 2)
    return []


NON_ARTIFACT_MARKERS = {
    "/.hermes/skills/",
    "\\.hermes\\skills\\",
    "/node_modules/",
    "\\node_modules\\",
}
ARTIFACT_PATH_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:\\|/mnt/[^/]+/|/home/|/tmp/|(?:\.?/)?(?:output|outputs|artifacts|reports|ppt_decks|deep-research-reports)/)[^\"'<>|`\r\n]+?\.(?:md|html?|pptx|png|jpe?g|csv|xlsx|json))",
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


def _configured_hermes_home_candidates() -> list[Path]:
    configured = settings.hermes_home.strip() or "~/.hermes"
    if os.name != "nt" or not configured.startswith("/"):
        return [Path(configured).expanduser()]

    distro = settings.hermes_wsl_distribution.strip() or "Ubuntu"
    relative = configured.lstrip("/").replace("/", "\\")
    return [
        Path(f"\\\\wsl.localhost\\{distro}\\{relative}"),
        Path(f"\\\\wsl$\\{distro}\\{relative}"),
    ]


def _candidate_roots() -> list[Path]:
    repo_root = _repo_root()
    user_home = Path.home()
    roots = [
        repo_root / "reports",
        repo_root / "deep-research-reports",
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
    ]
    for hermes_home in _configured_hermes_home_candidates():
        roots.extend(
            [
                hermes_home / "reports",
                hermes_home / "deep-research-reports",
                hermes_home / "images",
                hermes_home / "plans",
            ]
        )
    deduped: list[Path] = []
    seen_roots: set[str] = set()
    for root in roots:
        key = _normalized_path_key(root)
        if key in seen_roots:
            continue
        seen_roots.add(key)
        deduped.append(root)
    return deduped


def _resolve_bare_artifact_filename(filename: str) -> Path | None:
    name = Path(filename).name
    if (
        not name
        or name.lower() in IGNORED_FILENAMES
        or Path(name).suffix.lower() not in SUPPORTED_SUFFIXES
    ):
        return None

    candidates: list[Path] = []
    direct_roots = [Path.cwd(), _repo_root(), _repo_root() / "services" / "api"]
    for root in direct_roots:
        direct_candidate = root / name
        if _is_regular_artifact_candidate(direct_candidate):
            candidates.append(direct_candidate)

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
    return [home / "sessions" for home in _configured_hermes_home_candidates()]


def _runtime_artifacts_dir(run_id: str | None) -> Path:
    if run_id:
        return run_artifacts_dir(run_id)
    path = _repo_root() / "runtime" / "agent-runs" / "unbound" / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_ignored(path: Path) -> bool:
    normalized_parts = tuple(part.lower() for part in path.parts)
    if any(part in IGNORED_PARTS for part in normalized_parts):
        return True
    if any(part.endswith(IGNORED_PART_SUFFIXES) for part in normalized_parts):
        return True
    return False


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
            [
                "wsl.exe",
                "-d",
                settings.hermes_wsl_distribution,
                "--",
                "stat",
                "-c",
                "%F:%Y",
                wsl_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
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
                ["wsl.exe", "-d", settings.hermes_wsl_distribution, "--", "cat", wsl_path],
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
    normalized_parts = {part.lower() for part in parts}
    if parts and parts[0] == "agent-runs":
        return False
    if len(parts) >= 3 and parts[0] == "hermes-runs":
        return "artifacts" not in normalized_parts
    if parts and parts[0] == "users":
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
    wsl_match = re.match(r"^//(?:wsl\.localhost|wsl\$)/[^/]+/(.*)$", value, re.IGNORECASE)
    if wsl_match:
        return "/" + wsl_match.group(1).lower()
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
    runtime_skill_markers = {
        "/.hermes/skills/",
        "/hermes-home/skills/",
    }

    if artifact_type == "debug_json" or filename in intermediate_names:
        return "intermediate"
    if filename == "skill.md" and any(marker in normalized for marker in runtime_skill_markers):
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
            columns = next(reader, None)
            if columns is None:
                return {}
            preview_rows: list[list[str]] = []
            row_count = 0
            for row in reader:
                row_count += 1
                if len(preview_rows) < 100:
                    preview_rows.append(row)
    except OSError:
        return {}

    return {
        "columns": columns,
        "rows": preview_rows,
        "summary": [
            {"label": "Rows", "value": str(row_count)},
            {"label": "Columns", "value": str(len(columns))},
        ],
    }


def _image_metadata(path: Path) -> dict:
    return {
        "images": [
            {
                "id": _artifact_id(path),
                "prompt": path.stem,
            }
        ]
    }


def _metadata(
    path: Path,
    artifact_type: ArtifactType,
    *,
    content_hash: str | None = None,
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
        "contentHash": content_hash or _file_sha256(path),
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
    content_hash: str | None = None,
    metadata_extra: dict[str, Any] | None = None,
    original_path: str | None = None,
    title_override: str | None = None,
) -> schemas.Artifact | None:
    if not _is_regular_artifact_candidate(path):
        return None
    original_name = Path(original_path).name.lower() if original_path else ""
    if path.name.lower() in IGNORED_FILENAMES or original_name in IGNORED_FILENAMES:
        return None
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return None

    artifact_type = _valid_artifact_type(artifact_type_override, _artifact_type(path))
    metadata = _metadata(
        path,
        artifact_type,
        content_hash=content_hash,
        original_path=original_path,
    )
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
        is_primary=metadata.get("artifactRole") == "primary",
    )


def _normalize_path(raw_path: str) -> Path:
    match = raw_path.strip().strip(".,;:)]}\"'").replace("\\", "/")
    relative_match = match.lstrip("./")
    if relative_match.startswith(
        (
            "output/",
            "outputs/",
            "artifacts/",
            "reports/",
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
        if os.name == "nt":
            distro = settings.hermes_wsl_distribution.strip() or "Ubuntu"
            return Path(f"\\\\wsl.localhost\\{distro}") / match.lstrip("/").replace(
                "/", "\\"
            )
        return Path(match)
    return Path(raw_path.strip().strip(".,;:)]}\"'"))


def _archive_artifact_path(
    path: Path,
    run_id: str | None,
    archive_dir: Path | None = None,
) -> Path:
    if not run_id:
        return path
    if not _is_regular_artifact_candidate(path):
        return path

    artifact_dir = (archive_dir or _runtime_artifacts_dir(run_id)).expanduser().resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    try:
        path.resolve().relative_to(artifact_dir)
    except ValueError:
        pass
    else:
        return path
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
    *,
    archive_dir: Path | None = None,
) -> list[schemas.Artifact]:
    artifacts: list[schemas.Artifact] = []

    for raw_path in paths:
        path = _normalize_path(raw_path)
        if _is_non_artifact_path(raw_path) or _is_non_artifact_path(path):
            continue
        # Explicit adapter/event paths are authoritative. Hermes may write a
        # requested final artifact under its run-scoped home/context directory;
        # broad scans still exclude that directory, but an explicit path must
        # remain discoverable. Conversation input artifacts are removed later
        # by content-hash/path deduplication.
        if run_id is None and _is_repo_runtime_temp_path(path):
            continue
        readable_path, temp_dir = _materialize_wsl_artifact(path)
        try:
            archived_path = _archive_artifact_path(readable_path, run_id, archive_dir)
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
        artifacts.append(artifact)
    artifacts = dedupe_discovered_artifacts(artifacts)
    artifacts.sort(
        key=lambda artifact: str((artifact.metadata or {}).get("updatedAt", "")),
        reverse=True,
    )
    return artifacts


def create_artifacts_from_refs(
    session_id: str,
    artifact_refs: list[object],
    run_id: str | None = None,
    *,
    archive_dir: Path | None = None,
) -> list[schemas.Artifact]:
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
        entry_id = (
            getattr(artifact_ref, "entry_id", None)
            if not isinstance(artifact_ref, dict)
            else artifact_ref.get("entry_id") or artifact_ref.get("entryId")
        )
        role = (
            getattr(artifact_ref, "role", None)
            if not isinstance(artifact_ref, dict)
            else artifact_ref.get("role")
        )
        ref_status = (
            getattr(artifact_ref, "status", None)
            if not isinstance(artifact_ref, dict)
            else artifact_ref.get("status")
        )
        discovered_by = (
            getattr(artifact_ref, "discovered_by", None)
            if not isinstance(artifact_ref, dict)
            else artifact_ref.get("discovered_by") or artifact_ref.get("discoveredBy")
        )
        path_scope = (
            getattr(artifact_ref, "path_scope", None)
            if not isinstance(artifact_ref, dict)
            else artifact_ref.get("path_scope") or artifact_ref.get("pathScope")
        )
        expected_size = (
            getattr(artifact_ref, "size_bytes", None)
            if not isinstance(artifact_ref, dict)
            else artifact_ref.get("size_bytes") or artifact_ref.get("sizeBytes")
        )
        expected_sha256 = (
            getattr(artifact_ref, "sha256", None)
            if not isinstance(artifact_ref, dict)
            else artifact_ref.get("sha256")
        )
        manifest_schema = (
            getattr(artifact_ref, "manifest_schema", None)
            if not isinstance(artifact_ref, dict)
            else artifact_ref.get("manifest_schema") or artifact_ref.get("manifestSchema")
        )
        manifest_path = (
            getattr(artifact_ref, "manifest_path", None)
            if not isinstance(artifact_ref, dict)
            else artifact_ref.get("manifest_path") or artifact_ref.get("manifestPath")
        )
        if ref_status and ref_status != "ready":
            continue

        path = _normalize_path(path_value)
        if _is_non_artifact_path(path_value) or _is_non_artifact_path(path):
            continue
        # Adapter refs are an explicit artifact protocol response. Do not drop
        # them solely because Hermes placed the output in a run-scoped runtime
        # directory; generic filesystem scans retain the stricter exclusion.
        if run_id is None and _is_repo_runtime_temp_path(path):
            continue
        readable_path, temp_dir = _materialize_wsl_artifact(path)
        try:
            if isinstance(expected_size, int) and readable_path.stat().st_size != expected_size:
                raise RuntimeError(
                    f"Artifact manifest size mismatch for {path}: "
                    f"expected {expected_size}, got {readable_path.stat().st_size}."
                )
            actual_sha256 = _file_sha256(readable_path)
            if (
                isinstance(expected_sha256, str)
                and expected_sha256
                and actual_sha256 != expected_sha256
            ):
                raise RuntimeError(f"Artifact manifest checksum mismatch for {path}.")
            archived_path = _archive_artifact_path(readable_path, run_id, archive_dir)
            artifact = _artifact_from_path(
                session_id,
                archived_path,
                artifact_type_override=artifact_type,
                content_hash=actual_sha256,
                metadata_extra={
                    "adapterProtocol": manifest_schema or "hermes.artifact.v1",
                    "adapterRunId": ref_run_id,
                    "adapterSourceDir": source_dir,
                    "adapterTitle": title,
                    "adapterType": artifact_type,
                    "artifactRole": role,
                    "manifestEntryId": entry_id,
                    "manifestDiscoveredBy": discovered_by,
                    "manifestPathScope": path_scope,
                    "manifestExpectedSize": expected_size,
                    "manifestExpectedSha256": expected_sha256,
                    "manifestIntegrityVerified": bool(
                        manifest_schema in SUPPORTED_ARTIFACT_MANIFEST_SCHEMAS
                        and actual_sha256
                        and actual_sha256 == expected_sha256
                    ),
                    "protocolManifestPath": manifest_path,
                },
                original_path=str(path),
                title_override=title if isinstance(title, str) and title else None,
            )
        finally:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)
        if artifact is None:
            continue

        artifacts.append(artifact)
    manifest_artifacts = [
        artifact
        for artifact in artifacts
        if (artifact.metadata or {}).get("adapterProtocol")
        in SUPPORTED_ARTIFACT_MANIFEST_SCHEMAS
    ]
    legacy_artifacts = [artifact for artifact in artifacts if artifact not in manifest_artifacts]
    artifacts = manifest_artifacts + dedupe_discovered_artifacts(legacy_artifacts)
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
            discovered.append(artifact)
    discovered = dedupe_discovered_artifacts(discovered)
    discovered.sort(
        key=lambda artifact: str((artifact.metadata or {}).get("updatedAt", "")),
        reverse=True,
    )
    return discovered
