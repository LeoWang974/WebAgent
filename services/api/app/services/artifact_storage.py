import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from os import name as os_name
from pathlib import Path

from app.core.config import settings

MANIFEST_SCHEMA = "webagent.artifacts.v1"


def safe_storage_segment(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value).strip(" .-")
    return cleaned[:96] or fallback


def artifact_storage_root() -> Path:
    configured = settings.artifact_storage_root.strip()
    if os_name != "nt" and re.match(r"^[A-Za-z]:[\\/]", configured):
        configured = "runtime/artifacts"
    root = Path(configured).expanduser()
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[4] / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def artifact_run_storage_dir(user_id: str, conversation_id: str, run_id: str) -> Path:
    path = (
        artifact_storage_root()
        / "users"
        / safe_storage_segment(user_id, "user")
        / "conversations"
        / safe_storage_segment(conversation_id, "conversation")
        / "runs"
        / safe_storage_segment(run_id, "run")
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class StoredArtifactFile:
    path: Path
    run_dir: Path
    category: str
    content_hash: str


def store_artifact_file(
    source: Path,
    *,
    user_id: str,
    conversation_id: str,
    run_id: str,
    is_primary: bool,
) -> StoredArtifactFile:
    run_dir = artifact_run_storage_dir(user_id, conversation_id, run_id)
    category = "primary" if is_primary else "intermediate"
    target_dir = run_dir / category
    target_dir.mkdir(parents=True, exist_ok=True)

    content_hash = file_sha256(source)
    destination = target_dir / (
        f"{safe_storage_segment(source.stem, 'artifact')}-{content_hash[:12]}"
        f"{source.suffix.lower()}"
    )
    if not destination.exists():
        temporary = destination.with_suffix(f"{destination.suffix}.tmp")
        try:
            shutil.copy2(source, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

    return StoredArtifactFile(
        path=destination,
        run_dir=run_dir,
        category=category,
        content_hash=content_hash,
    )


def update_artifact_manifest(run_dir: Path, entry: dict[str, object]) -> Path:
    manifest_path = run_dir / "manifest.json"
    manifest: dict[str, object] = {
        "schema": MANIFEST_SCHEMA,
        "updatedAt": datetime.now(UTC).isoformat(),
        "artifacts": [],
    }
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and loaded.get("schema") == MANIFEST_SCHEMA:
                manifest.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass

    existing_entries = manifest.get("artifacts", [])
    if not isinstance(existing_entries, list):
        existing_entries = []
    entries = [
        item
        for item in existing_entries
        if isinstance(item, dict) and item.get("artifactId") != entry.get("artifactId")
    ]
    entries.append(entry)
    manifest["artifacts"] = entries
    manifest["updatedAt"] = datetime.now(UTC).isoformat()

    temporary = manifest_path.with_suffix(".json.tmp")
    try:
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(manifest_path)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest_path
