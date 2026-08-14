import re
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.models import AgentRun, AgentRunEvent, Artifact, Message, UserSettings
from app.services.artifact_discovery import (
    discover_artifacts_with_retry,
    discover_related_artifact_paths,
    extract_artifact_path_strings,
)
from app.services.persistence import persist_message
from app.services.session_artifacts import (
    artifact_display_priority,
    is_debug_artifact,
    metadata_path_key,
    persist_discovered_artifacts,
)
from app.services.settings_service import DEFAULT_INTERFACE

FATAL_RUNTIME_PATTERNS = (
    re.compile(r"ratelimiterror|rate limit|http 429|rpm exhausted", re.IGNORECASE),
    re.compile(r"api call failed|invalid token|missing authentication header", re.IGNORECASE),
    re.compile(
        r"finish_reason='length'|response truncated|truncated tool call|output length limit",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:http(?: status| error)?|status(?: code)?|error code|code)\s*[:=]?\s*401\b"
        r"|\b401\s+(?:unauthorized|error)\b",
        re.IGNORECASE,
    ),
)

def _diagnostic_text(adapter: object, assistant_output: str) -> str:
    diagnostics = getattr(adapter, "last_diagnostics", {}) or {}
    parts = [assistant_output]
    for key in ("stderr_tail", "stdout_tail", "last_stage"):
        value = diagnostics.get(key)
        if value:
            parts.append(str(value))
    return "\n".join(parts)


def raise_for_fatal_runtime_diagnostics(adapter: object, assistant_output: str) -> None:
    diagnostic_text = _diagnostic_text(adapter, assistant_output)
    if not any(pattern.search(diagnostic_text) for pattern in FATAL_RUNTIME_PATTERNS):
        return
    tail = diagnostic_text.strip()[-800:] or "Hermes reported a model/API failure."
    raise RuntimeError(f"Hermes reported a model/API failure: {tail}")


def _adapter_artifact_paths(adapter: object) -> tuple[list[str], list[object]]:
    paths = adapter.get_last_artifact_paths() if hasattr(adapter, "get_last_artifact_paths") else []
    artifacts = adapter.get_last_artifacts() if hasattr(adapter, "get_last_artifacts") else []
    if artifacts:
        paths = [
            str(getattr(artifact, "path", ""))
            for artifact in artifacts
            if getattr(artifact, "path", "")
        ]
    return list(dict.fromkeys(paths)), list(artifacts)


def filter_preexisting_artifact_schemas(
    discovered: list[schemas.Artifact],
    *,
    existing_hashes: set[str],
    existing_paths: set[str],
) -> tuple[list[schemas.Artifact], list[str]]:
    filtered: list[schemas.Artifact] = []
    excluded_paths: list[str] = []
    for artifact in discovered:
        metadata = artifact.metadata or {}
        content_hash = str(metadata.get("contentHash") or "")
        candidate_paths = {
            metadata_path_key(value)
            for value in (
                metadata.get("path"),
                metadata.get("originalPath"),
                metadata.get("normalizedPath"),
                metadata.get("originalNormalizedPath"),
            )
            if isinstance(value, str) and value
        }
        if (content_hash and content_hash in existing_hashes) or candidate_paths.intersection(
            existing_paths
        ):
            excluded_paths.append(
                str(metadata.get("originalPath") or metadata.get("path") or artifact.title)
            )
            continue
        filtered.append(artifact)
    return filtered, excluded_paths


async def _existing_conversation_artifact_fingerprints(
    db: AsyncSession,
    conversation_id: str,
    run_id: str,
) -> tuple[set[str], set[str]]:
    result = await db.execute(
        select(Artifact).where(
            Artifact.conversation_id == conversation_id,
            or_(Artifact.run_id.is_(None), Artifact.run_id != run_id),
        )
    )
    hashes: set[str] = set()
    paths: set[str] = set()
    for artifact in result.scalars().all():
        metadata = artifact.artifact_metadata or {}
        content_hash = metadata.get("contentHash")
        if isinstance(content_hash, str) and content_hash:
            hashes.add(content_hash)
        for value in (
            metadata.get("path"),
            metadata.get("originalPath"),
            metadata.get("normalizedPath"),
            metadata.get("originalNormalizedPath"),
        ):
            if isinstance(value, str) and value:
                paths.add(metadata_path_key(value))
    return hashes, paths


async def _event_artifact_paths(db: AsyncSession, run_id: str) -> list[str]:
    result = await db.execute(select(AgentRunEvent).where(AgentRunEvent.run_id == run_id))
    paths: list[str] = []
    for event in result.scalars().all():
        for path in extract_artifact_path_strings(event.payload or {}):
            if path not in paths:
                paths.append(path)
    return paths


async def discover_and_persist_run_artifacts(
    db: AsyncSession,
    run: AgentRun,
    conversation_id: str,
    run_started_at: datetime,
    adapter: object,
    artifact_discovery_summary: dict[str, object],
    user_id: str,
    content: str = "",
    assistant_output: str = "",
):
    """Discover and persist Hermes outputs without interpreting the user prompt.

    Explicit paths emitted by Hermes are authoritative. Paths present in persisted
    events and a run-scoped filesystem scan are generic recovery mechanisms only;
    WebAgent never creates a replacement report, HTML page, or PPTX.
    """

    run_id = run.id
    explicit_paths, explicit_artifacts = _adapter_artifact_paths(adapter)
    for path in await _event_artifact_paths(db, run_id):
        if path not in explicit_paths:
            explicit_paths.append(path)

    referenced_paths = extract_artifact_path_strings(content)
    referenced_paths.extend(
        path
        for path in extract_artifact_path_strings(assistant_output)
        if path not in referenced_paths
    )
    related_paths = discover_related_artifact_paths(referenced_paths, run_started_at)
    for path in related_paths:
        if path not in explicit_paths:
            explicit_paths.append(path)

    artifact_discovery_summary.update(
        {
            "explicit_artifact_paths": list(explicit_paths),
            "referenced_paths": referenced_paths,
            "related_artifact_paths": related_paths,
        }
    )

    if explicit_paths or explicit_artifacts:
        discovered = await discover_artifacts_with_retry(
            conversation_id,
            run_started_at,
            explicit_paths,
            run_id,
            explicit_artifacts,
        )
    else:
        discovered = []

    existing_hashes, existing_paths = await _existing_conversation_artifact_fingerprints(
        db,
        conversation_id,
        run_id,
    )
    discovered, excluded_context_paths = filter_preexisting_artifact_schemas(
        discovered,
        existing_hashes=existing_hashes,
        existing_paths=existing_paths,
    )
    artifact_discovery_summary["excluded_context_artifact_paths"] = excluded_context_paths

    stored = await persist_discovered_artifacts(db, conversation_id, discovered, run_id)
    current_run_artifacts = [artifact for artifact in stored if artifact.run_id == run_id]
    external_artifacts = [
        artifact
        for artifact in current_run_artifacts
        if (artifact.artifact_metadata or {}).get("outputPathCompliant") is False
    ]
    artifact_discovery_summary["path_compliance"] = {
        "compliant_count": len(current_run_artifacts) - len(external_artifacts),
        "external_count": len(external_artifacts),
        "external_paths": [
            str((artifact.artifact_metadata or {}).get("originalPath") or "")
            for artifact in external_artifacts
        ],
        "runtime_instruction_injected": False,
    }
    if not current_run_artifacts:
        raise_for_fatal_runtime_diagnostics(adapter, assistant_output)

    primary_artifacts = [
        artifact
        for artifact in current_run_artifacts
        if artifact.is_primary and not is_debug_artifact(artifact)
    ]
    artifact_discovery_summary["primary_artifact_count"] = len(primary_artifacts)
    artifact_discovery_summary["primary_artifact_types"] = sorted(
        {artifact.type for artifact in primary_artifacts}
    )
    developer_mode = await user_developer_mode_by_id(db, user_id)
    visible = [
        artifact
        for artifact in current_run_artifacts
        if developer_mode or not is_debug_artifact(artifact)
    ]
    artifact_discovery_summary["stored_count"] = len(stored)
    artifact_discovery_summary["visible_count"] = len(visible)
    return sorted(visible, key=artifact_display_priority)


async def final_assistant_message(
    db: AsyncSession,
    conversation_id: str,
    assistant_messages: list[Message],
    response_artifacts,
) -> Message:
    if assistant_messages:
        assistant_message = assistant_messages[-1]
        if response_artifacts:
            assistant_message.artifact_ids = [artifact.id for artifact in response_artifacts]
            await db.commit()
            await db.refresh(assistant_message)
        return assistant_message
    return await persist_message(
        db,
        conversation_id,
        "assistant",
        (
            "Hermes completed and generated artifacts."
            if response_artifacts
            else "Hermes completed without a visible status update."
        ),
        [artifact.id for artifact in response_artifacts] or None,
    )


async def user_developer_mode_by_id(db: AsyncSession, user_id: str) -> bool:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    user_settings = result.scalar_one_or_none()
    if user_settings is None:
        user_settings = UserSettings(
            user_id=user_id,
            data_context={},
            interface=DEFAULT_INTERFACE,
        )
        db.add(user_settings)
        await db.commit()
        await db.refresh(user_settings)
    interface = user_settings.interface or {}
    return bool(interface.get("developer_mode", interface.get("developerMode", False)))
