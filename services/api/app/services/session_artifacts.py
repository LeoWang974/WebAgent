import hashlib
import re
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import schemas
from app.core.config import settings
from app.models import Artifact, Conversation, ConversationShare


def is_primary_report_artifact(artifact: Artifact) -> bool:
    path = str((artifact.artifact_metadata or {}).get("path", "")).lower()
    title = artifact.title.lower()
    return artifact.type == "markdown_report" and (
        path.endswith("report.md")
        or path.endswith("final_report.md")
        or title in {"report", "final_report", "final-report"}
    )


def artifact_display_priority(artifact: Artifact) -> tuple[int, datetime]:
    type_priority = {
        "debug_json": 1,
        "markdown_report": 10,
        "data_table": 20,
        "chart": 30,
        "html_page": 40,
        "ppt_deck": 80,
        "image_result": 90,
    }
    return (type_priority.get(artifact.type, 0), artifact.created_at)


def is_debug_artifact(artifact: Artifact) -> bool:
    return artifact.type == "debug_json"


def artifact_metadata_paths(metadata: dict) -> list[Path]:
    paths = []
    for key in ("path", "originalPath"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            paths.append(Path(value))
    return paths


def file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def artifact_content_hash(artifact: Artifact) -> str | None:
    metadata = dict(artifact.artifact_metadata or {})
    content_hash = metadata.get("contentHash")
    if isinstance(content_hash, str) and content_hash:
        return content_hash
    for path in artifact_metadata_paths(metadata):
        content_hash = file_sha256(path)
        if content_hash:
            metadata["contentHash"] = content_hash
            artifact.artifact_metadata = metadata
            return content_hash
    return None


def artifact_dedupe_keys(metadata: dict) -> tuple[str, list[str]]:
    content_hash = str(metadata.get("contentHash") or "")
    candidate_paths = [
        str(value)
        for value in {
            metadata.get("path"),
            metadata.get("originalPath"),
            metadata.get("normalizedPath"),
            metadata.get("originalNormalizedPath"),
        }
        if isinstance(value, str) and value
    ]
    return content_hash, candidate_paths


def metadata_path_key(path: str | Path) -> str:
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


def safe_storage_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value).strip(" .-")
    return cleaned[:80] or fallback


def organize_artifact_schema(
    artifact_schema: schemas.Artifact,
    conversation: Conversation,
    run_id: str | None = None,
) -> schemas.Artifact:
    if not settings.artifact_storage_enabled:
        return artifact_schema

    metadata = dict(artifact_schema.metadata or {})
    raw_path = metadata.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return artifact_schema

    source = Path(raw_path)
    if not source.exists() or not source.is_file():
        return artifact_schema

    storage_root = Path(settings.artifact_storage_root)
    folder_label = safe_storage_name(conversation.title or "conversation", "conversation")
    conversation_dir = storage_root / f"{folder_label}-{conversation.id[:8]}"
    target_dir = conversation_dir / f"run-{run_id[:8]}" if run_id else conversation_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha1(str(source).encode("utf-8", errors="ignore")).hexdigest()[:10]
    destination = target_dir / f"{source.stem}-{digest}{source.suffix.lower()}"
    if destination.exists() and destination.stat().st_mtime >= source.stat().st_mtime:
        stored_path = destination
    else:
        runtime_root = Path(__file__).resolve().parents[4] / "runtime"
        try:
            source.relative_to(runtime_root)
            shutil.move(str(source), destination)
        except ValueError:
            shutil.copy2(source, destination)
        stored_path = destination

    if not metadata.get("originalPath"):
        metadata["originalPath"] = str(source)
        metadata["originalNormalizedPath"] = metadata_path_key(source)
    metadata["path"] = str(stored_path)
    metadata["normalizedPath"] = metadata_path_key(stored_path)
    metadata["storageRoot"] = str(storage_root)
    metadata["storageConversationDir"] = str(conversation_dir)
    metadata["storageRunDir"] = str(target_dir)
    metadata["organizedAt"] = datetime.now().isoformat()
    artifact_schema.metadata = metadata
    return artifact_schema


async def find_existing_artifact(
    db: AsyncSession,
    session_id: str,
    artifact_type: str,
    metadata: dict,
) -> Artifact | None:
    content_hash, candidate_paths = artifact_dedupe_keys(metadata)
    if content_hash:
        result = await db.execute(
            select(Artifact).where(
                Artifact.conversation_id == session_id,
                Artifact.artifact_metadata["contentHash"].as_string() == content_hash,
            )
        )
        existing_artifact = result.scalar_one_or_none()
        if existing_artifact is not None:
            return existing_artifact

    if candidate_paths:
        result = await db.execute(
            select(Artifact).where(
                Artifact.conversation_id == session_id,
                or_(
                    Artifact.artifact_metadata["path"].as_string().in_(candidate_paths),
                    Artifact.artifact_metadata["originalPath"].as_string().in_(candidate_paths),
                    Artifact.artifact_metadata["normalizedPath"].as_string().in_(candidate_paths),
                    Artifact.artifact_metadata["originalNormalizedPath"]
                    .as_string()
                    .in_(candidate_paths),
                ),
            )
        )
        existing_artifact = result.scalar_one_or_none()
        if existing_artifact is not None:
            return existing_artifact

    if content_hash:
        result = await db.execute(
            select(Artifact).where(
                Artifact.conversation_id == session_id,
                Artifact.type == artifact_type,
            )
        )
        for candidate_artifact in result.scalars().all():
            if artifact_content_hash(candidate_artifact) == content_hash:
                return candidate_artifact

    return None


async def refresh_conversation(db: AsyncSession, session_id: str) -> Conversation:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == session_id)
        .options(selectinload(Conversation.shares).selectinload(ConversationShare.user))
        .execution_options(populate_existing=True)
    )
    conversation = result.scalar_one()
    return conversation


async def persist_discovered_artifacts(
    db: AsyncSession,
    session_id: str,
    discovered_artifacts: list[schemas.Artifact],
    run_id: str | None = None,
) -> list[Artifact]:
    stored_artifacts: list[Artifact] = []
    conversation = await refresh_conversation(db, session_id)

    for artifact_schema in discovered_artifacts:
        artifact_schema = organize_artifact_schema(artifact_schema, conversation, run_id)
        metadata = artifact_schema.metadata or {}
        existing_artifact = await find_existing_artifact(
            db,
            session_id,
            artifact_schema.type,
            metadata,
        )
        if existing_artifact is not None:
            stored_artifacts.append(existing_artifact)
            continue

        artifact = Artifact(
            conversation_id=session_id,
            run_id=run_id,
            type=artifact_schema.type,
            title=artifact_schema.title,
            status=artifact_schema.status,
            content=artifact_schema.content,
            artifact_metadata=artifact_schema.metadata,
        )
        db.add(artifact)
        stored_artifacts.append(artifact)

    if stored_artifacts:
        await db.commit()
        for artifact in stored_artifacts:
            await db.refresh(artifact)

    return stored_artifacts
