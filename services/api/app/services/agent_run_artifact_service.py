# File purpose: Implements the agent run artifact service backend service workflow.
# Main declarations: _diagnostic_text handles diagnostic text; raise_for_fatal_runtime_diagnostics
# handles raise for fatal runtime diagnostics; _adapter_artifact_paths handles adapter artifact
# paths; _event_artifact_paths handles event artifact paths;
# discover_and_persist_run_artifacts discovers and persist run artifacts; final_assistant_message
# handles final assistant message; user_developer_mode_by_id handles user developer mode by id.

import asyncio
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun, AgentRunEvent, Artifact, Message, UserSettings
from app.schemas.artifact_manifest import ArtifactManifest
from app.services.agent_run_workspace import run_artifacts_dir
from app.services.artifact_discovery import (
    discover_artifacts_with_retry,
    discover_related_artifact_paths,
    extract_artifact_path_strings,
)
from app.services.artifact_storage import store_protocol_artifact_manifest
from app.services.persistence import persist_message
from app.services.session_artifacts import (
    artifact_display_priority,
    is_debug_artifact,
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
    re.compile(
        r"stream stalled|action was not executed|tool-call[^\n]*not executed",
        re.IGNORECASE,
    ),
)

EXPLICIT_OUTPUT_PATH_RE = re.compile(
    r"(?:(?:保存|输出|导出)(?:文件)?(?:到|至|为)?|save\s+as|write\s+to|export\s+to)"
    r"\s*[`\"']?(?P<path>[^`\"'\r\n]+?\.(?:md|html?|pptx|png|jpe?g|csv|xlsx))",
    re.IGNORECASE,
)
EXPLICIT_ARTIFACT_SUFFIX_RE = re.compile(
    r"(?P<path>\.(?:md|html?|pptx|png|jpe?g|csv|xlsx))\b",
    re.IGNORECASE,
)
ARTIFACT_TYPE_BY_SUFFIX = {
    ".md": "markdown_report",
    ".html": "html_page",
    ".htm": "html_page",
    ".pptx": "ppt_deck",
    ".png": "image_result",
    ".jpg": "image_result",
    ".jpeg": "image_result",
    ".csv": "data_table",
    ".xlsx": "data_table",
}
# JSON is intentionally absent: debug/intermediate JSON remains discoverable
# as debug_json, but it is not a user-facing primary output contract.
ARTIFACT_EVENT_TYPES = {
    "artifact_found",
    "artifact_manifest_finalized",
    "artifact_state",
    "completed",
}


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


def explicit_requested_artifact_type(content: str) -> str | None:
    matches = list(EXPLICIT_OUTPUT_PATH_RE.finditer(content))
    if not matches:
        matches = list(EXPLICIT_ARTIFACT_SUFFIX_RE.finditer(content))
    if not matches:
        return None
    requested_path = matches[-1].group("path").strip()
    suffix = (
        requested_path.lower()
        if requested_path.lower() in ARTIFACT_TYPE_BY_SUFFIX
        else Path(requested_path).suffix.lower()
    )
    return ARTIFACT_TYPE_BY_SUFFIX.get(suffix)


def validate_explicit_output_artifact(content: str, artifacts: list[Artifact]) -> None:
    expected_type = explicit_requested_artifact_type(content)
    if expected_type is None:
        return
    produced_types = {artifact.type for artifact in artifacts if artifact.is_primary}
    if expected_type not in produced_types:
        raise RuntimeError(
            "Hermes completed without producing the explicitly requested "
            f"{expected_type} artifact."
        )


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


def _adapter_artifact_manifest(adapter: object) -> ArtifactManifest | None:
    if not hasattr(adapter, "get_last_artifact_manifest"):
        return None
    payload = adapter.get_last_artifact_manifest()
    if not payload:
        return None
    return ArtifactManifest.model_validate(payload)


def _manifest_artifact_refs(
    manifest: ArtifactManifest,
    *,
    persisted_manifest_path: str,
) -> list[dict[str, object]]:
    return [
        {
            "path": entry.path,
            "artifact_type": entry.artifact_type,
            "run_id": manifest.run_id,
            "source_dir": entry.source_dir,
            "path_scope": entry.path_scope,
            "title": entry.title,
            "entry_id": entry.entry_id,
            "role": entry.role,
            "status": entry.status,
            "discovered_by": entry.discovered_by,
            "size_bytes": entry.size_bytes,
            "sha256": entry.sha256,
            "manifest_schema": manifest.schema_version,
            "manifest_path": persisted_manifest_path,
        }
        for entry in manifest.artifacts
        if entry.status == "ready"
    ]


async def _event_artifact_paths(db: AsyncSession, run_id: str) -> list[str]:
    result = await db.execute(
        select(AgentRunEvent.payload).where(
            AgentRunEvent.run_id == run_id,
            AgentRunEvent.event_type.in_(ARTIFACT_EVENT_TYPES),
        )
    )
    return list(
        dict.fromkeys(
            path
            for payload in result.scalars().all()
            for path in extract_artifact_path_strings(payload or {})
        )
    )


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
    manifest = _adapter_artifact_manifest(adapter)
    if manifest is not None:
        if manifest.run_id != run_id:
            raise RuntimeError(
                f"Artifact manifest run mismatch: expected {run_id}, got {manifest.run_id}."
            )
        if manifest.status == "collecting":
            raise RuntimeError("Artifact manifest was not finalized before Agent Run completion.")
        if manifest.status == "failed":
            detail = "; ".join(manifest.errors) or "unknown manifest failure"
            raise RuntimeError(f"Artifact manifest failed: {detail}")
        unresolved_entries = [
            entry for entry in manifest.artifacts if entry.status in {"pending", "staging"}
        ]
        if unresolved_entries:
            unresolved_paths = ", ".join(entry.path for entry in unresolved_entries[:5])
            raise RuntimeError(
                f"Artifact manifest contains files that never stabilized: {unresolved_paths}"
            )
        persisted_manifest_path = await asyncio.to_thread(
            store_protocol_artifact_manifest,
            manifest.model_dump(mode="json", by_alias=True),
            user_id=user_id,
            conversation_id=conversation_id,
            run_id=run_id,
        )
        explicit_artifacts = _manifest_artifact_refs(
            manifest,
            persisted_manifest_path=str(persisted_manifest_path),
        )
        explicit_paths = [
            entry.path for entry in manifest.artifacts if entry.status == "ready"
        ]
        referenced_paths: list[str] = []
        related_paths: list[str] = []
        artifact_discovery_summary["manifest"] = {
            "schema": manifest.schema_version,
            "status": manifest.status,
            "producer": manifest.producer,
            "entry_count": len(manifest.artifacts),
            "ready_count": sum(
                entry.status == "ready" for entry in manifest.artifacts
            ),
            "failed_count": sum(
                entry.status in {"failed", "missing"} for entry in manifest.artifacts
            ),
            "recovery_used": manifest.recovery_used,
            "errors": list(manifest.errors),
            "persisted_path": str(persisted_manifest_path),
        }
    else:
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
        related_paths = await asyncio.to_thread(
            discover_related_artifact_paths,
            referenced_paths,
            run_started_at,
        )
        for path in related_paths:
            if path not in explicit_paths:
                explicit_paths.append(path)
        artifact_discovery_summary["manifest"] = {
            "schema": None,
            "status": "legacy_fallback",
            "entry_count": len(explicit_artifacts),
            "recovery_used": True,
        }

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
            archive_dir=run_artifacts_dir(run_id, conversation_id, user_id),
            authoritative_manifest=manifest is not None,
        )
    else:
        discovered = []

    # A path or content hash seen in an older Run must never suppress the
    # current Run's ownership. Current-run dedupe happens during persistence.
    artifact_discovery_summary["excluded_context_artifact_paths"] = []

    stored = await persist_discovered_artifacts(db, conversation_id, discovered, run_id)
    current_run_artifacts = stored
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
    validate_explicit_output_artifact(content, primary_artifacts)
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
            await db.flush()
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
        commit=False,
    )


async def user_developer_mode_by_id(db: AsyncSession, user_id: str) -> bool:
    result = await db.execute(
        select(UserSettings.interface).where(UserSettings.user_id == user_id)
    )
    interface = result.scalar_one_or_none() or DEFAULT_INTERFACE
    return bool(interface.get("developer_mode", interface.get("developerMode", False)))
