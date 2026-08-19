import hashlib
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import schemas
from app.core.config import settings
from app.models import Artifact, Conversation, ConversationShare
from app.services.agent_run_workspace import run_workspace_dir
from app.services.artifact_storage import (
    artifact_storage_root,
    store_artifact_file,
    update_artifact_manifest,
)
from app.services.runtime_environment import runtime_run_dir_for_ids


def is_primary_report_artifact(artifact: Artifact) -> bool:
    if is_debug_artifact(artifact):
        return False
    metadata = artifact.artifact_metadata or {}
    path = str(metadata.get("path") or metadata.get("originalPath") or "").lower()
    title = artifact.title.lower()
    return artifact.type == "markdown_report" and (
        path.endswith("report.md")
        or path.endswith("final_report.md")
        or "报告" in title
        or "report" in title
        or title in {"report", "final_report", "final-report"}
    )


def artifact_display_priority(artifact: Artifact) -> tuple[int, datetime]:
    if is_debug_artifact(artifact):
        return (0, artifact.created_at)
    type_priority = {
        "debug_json": 1,
        "data_table": 60,
        "chart": 60,
        "image_result": 70,
        "markdown_report": 75,
        "html_page": 90,
        "ppt_deck": 100,
    }
    priority = type_priority.get(artifact.type, 0)
    if not artifact.is_primary:
        priority = min(priority, 20)
    if is_primary_report_artifact(artifact):
        priority = max(priority, 80)
    return (priority, artifact.created_at)


def is_debug_artifact(artifact: Artifact) -> bool:
    metadata = artifact.artifact_metadata or {}
    return (
        artifact.type == "debug_json"
        or metadata.get("developerOnly") is True
        or metadata.get("artifactRole") == "intermediate"
        or (artifact.is_primary is False and metadata.get("artifactRole") == "preview_fallback")
    )


def is_primary_artifact_schema(artifact_schema: schemas.Artifact) -> bool:
    metadata = artifact_schema.metadata or {}
    if metadata.get("developerOnly") is True or metadata.get("artifactRole") == "intermediate":
        return False
    path = str(metadata.get("path") or metadata.get("originalPath") or "").replace("\\", "/")
    filename = str(metadata.get("filename") or "").lower()
    if artifact_schema.type == "debug_json":
        return False
    if artifact_schema.type == "html_page" and "/pages/" in path.lower() and filename.startswith(
        "page_"
    ):
        return False
    return True


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


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def artifact_source_location(
    source: Path,
    conversation: Conversation,
    run_id: str,
) -> tuple[str, bool]:
    managed_locations = {
        "run_workspace": run_workspace_dir(run_id, conversation.id, conversation.user_id),
        "runtime_home": runtime_run_dir_for_ids(
            conversation.user_id,
            conversation.id,
            run_id,
        ),
    }
    for location, root in managed_locations.items():
        if _path_is_within(source, root):
            return location, True
    return "external", False


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

    if not run_id:
        return artifact_schema

    is_primary = is_primary_artifact_schema(artifact_schema)
    original_path = metadata.get("originalPath")
    compliance_source = (
        Path(original_path)
        if isinstance(original_path, str) and original_path
        else source
    )
    source_location, output_path_compliant = artifact_source_location(
        compliance_source,
        conversation,
        run_id,
    )
    stored = store_artifact_file(
        source,
        user_id=conversation.user_id,
        conversation_id=conversation.id,
        run_id=run_id,
        is_primary=is_primary,
    )
    organized_at = datetime.now().astimezone().isoformat()

    if not original_path:
        metadata["originalPath"] = str(source)
        metadata["originalNormalizedPath"] = metadata_path_key(source)
    metadata["path"] = str(stored.path)
    metadata["normalizedPath"] = metadata_path_key(stored.path)
    metadata["contentHash"] = stored.content_hash
    metadata["storageRoot"] = str(artifact_storage_root())
    metadata["storageRunDir"] = str(stored.run_dir)
    metadata["storageCategory"] = stored.category
    metadata["sourceLocation"] = source_location
    metadata["outputPathCompliant"] = output_path_compliant
    metadata["runtimeInstructionInjected"] = False
    metadata["organizedAt"] = organized_at
    manifest_path = update_artifact_manifest(
        stored.run_dir,
        {
            "artifactId": artifact_schema.id,
            "conversationId": conversation.id,
            "runId": run_id,
            "type": artifact_schema.type,
            "title": artifact_schema.title,
            "status": artifact_schema.status,
            "isPrimary": is_primary,
            "storageCategory": stored.category,
            "contentHash": stored.content_hash,
            "originalPath": str(metadata["originalPath"]),
            "storedPath": str(stored.path),
            "sourceLocation": source_location,
            "outputPathCompliant": output_path_compliant,
            "runtimeInstructionInjected": False,
            "organizedAt": organized_at,
        },
    )
    metadata["manifestPath"] = str(manifest_path)
    artifact_schema.metadata = metadata
    artifact_schema.is_primary = is_primary
    return artifact_schema


def _artifact_match_keys(metadata: dict) -> set[str]:
    content_hash, candidate_paths = artifact_dedupe_keys(metadata)
    keys = {f"path:{metadata_path_key(path)}" for path in candidate_paths}
    if content_hash:
        keys.add(f"hash:{content_hash}")
    return keys


def _index_existing_artifacts(artifacts: list[Artifact]) -> dict[str, Artifact]:
    index: dict[str, Artifact] = {}
    for artifact in artifacts:
        metadata = artifact.artifact_metadata or {}
        keys = _artifact_match_keys(metadata)
        if not any(key.startswith("hash:") for key in keys):
            content_hash = artifact_content_hash(artifact)
            if content_hash:
                keys.add(f"hash:{content_hash}")
        for key in keys:
            index.setdefault(key, artifact)
    return index


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
    conditions = [Artifact.conversation_id == session_id]
    if run_id:
        conditions.append(Artifact.run_id == run_id)
    existing_result = await db.execute(select(Artifact).where(*conditions))
    existing_index = _index_existing_artifacts(list(existing_result.scalars().all()))

    for artifact_schema in discovered_artifacts:
        artifact_schema = organize_artifact_schema(artifact_schema, conversation, run_id)
        metadata = artifact_schema.metadata or {}
        match_keys = _artifact_match_keys(metadata)
        existing_artifact = next(
            (existing_index[key] for key in match_keys if key in existing_index),
            None,
        )
        if existing_artifact is not None:
            existing_artifact.type = artifact_schema.type
            existing_artifact.title = artifact_schema.title
            existing_artifact.status = artifact_schema.status
            existing_artifact.content = artifact_schema.content
            existing_artifact.artifact_metadata = metadata
            existing_artifact.is_primary = artifact_schema.is_primary
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
            is_primary=is_primary_artifact_schema(artifact_schema),
        )
        db.add(artifact)
        stored_artifacts.append(artifact)
        for key in match_keys:
            existing_index[key] = artifact

    if stored_artifacts:
        await db.commit()
        for artifact in stored_artifacts:
            await db.refresh(artifact)

    return stored_artifacts
