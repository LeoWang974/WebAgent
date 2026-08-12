from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.settings import DEFAULT_INTERFACE
from app.models import AgentRun, AgentRunEvent, Message, UserSettings
from app.services.artifact_discovery import (
    discover_artifacts_with_retry,
    discover_related_artifact_paths,
    extract_artifact_path_strings,
)
from app.services.persistence import persist_message
from app.services.session_artifacts import (
    artifact_display_priority,
    is_debug_artifact,
    persist_discovered_artifacts,
)

FATAL_RUNTIME_MARKERS = (
    "ratelimiterror",
    "rate limit",
    "http 429",
    "rpm exhausted",
    "api call failed",
    "invalid token",
    "missing authentication header",
    "finish_reason='length'",
    "response truncated",
    "truncated tool call",
    "output length limit",
    "401",
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
    if not any(marker in diagnostic_text.lower() for marker in FATAL_RUNTIME_MARKERS):
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

    stored = await persist_discovered_artifacts(db, conversation_id, discovered, run_id)
    current_run_artifacts = [artifact for artifact in stored if artifact.run_id == run_id]
    if not current_run_artifacts:
        raise_for_fatal_runtime_diagnostics(adapter, assistant_output)

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
