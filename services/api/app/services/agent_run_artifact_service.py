import asyncio
import re
import subprocess
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api.routes.settings import DEFAULT_INTERFACE, to_interface_schema
from app.core.config import settings
from app.models import AgentRun, AgentRunEvent, Artifact, Message, UserSettings
from app.services.agent_run_control import AgentRunTimeout
from app.services.artifact_discovery import (
    create_html_artifact_from_content,
    create_markdown_artifact_from_content,
    create_pptx_from_html_artifacts,
    discover_artifacts_since,
    discover_artifacts_with_retry,
    discover_related_artifact_paths,
    extract_artifact_path_strings,
)
from app.services.persistence import persist_message, to_artifact
from app.services.session_artifacts import (
    artifact_display_priority,
    is_debug_artifact,
    persist_discovered_artifacts,
)

PRIMARY_ARTIFACT_TYPES_BY_SKILL = {
    "data_analysis": {"data_table", "markdown_report", "html_page"},
    "deep_research": {"markdown_report", "html_page"},
    "html_generation": {"html_page"},
    "ppt_generation": {"ppt_deck"},
    "u1_image": {"image_result"},
}

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

PLACEHOLDER_OUTPUTS = {
    "hermes completed. discovering generated artifacts.",
    "openclaw completed. discovering generated artifacts.",
    "agent runtime completed without emitting a visible status update.",
}

DELAYED_DISCOVERY_ATTEMPTS_BY_TYPE = {
    "html_page": 6,
    "ppt_deck": 10,
}
DELAYED_DISCOVERY_INTERVAL_SECONDS = 10


REQUEST_ACTION_PATTERN = (
    r"(生成|制作|输出|导出|创建|转换|转成|做成|generate|create|export|convert|produce|make)"
)
NEGATIVE_CONTEXT_PATTERN = r"(不要|不需要|无需|不得|不是|非|no|not|without)"


def _mentions_requested_artifact(text: str, artifact_pattern: str) -> bool:
    return bool(
        re.search(rf"{REQUEST_ACTION_PATTERN}.{{0,24}}{artifact_pattern}", text, re.IGNORECASE)
        or re.search(
            rf"{artifact_pattern}.{{0,24}}{REQUEST_ACTION_PATTERN}",
            text,
            re.IGNORECASE,
        )
    )


def _has_positive_requested_artifact(text: str, artifact_pattern: str) -> bool:
    for match in re.finditer(artifact_pattern, text, re.IGNORECASE):
        if text[match.end() : match.end() + 1] in {"/", "／"}:
            continue
        context = text[max(0, match.start() - 32) : match.end() + 32]
        artifact_prefix = text[max(0, match.start() - 12) : match.start()]
        artifact_phrase = text[max(0, match.start() - 12) : match.end()]
        if re.search(NEGATIVE_CONTEXT_PATTERN, artifact_prefix, re.IGNORECASE) or re.search(
            rf"{NEGATIVE_CONTEXT_PATTERN}.{{0,12}}{artifact_pattern}",
            artifact_phrase,
            re.IGNORECASE,
        ):
            continue
        if _mentions_requested_artifact(context, artifact_pattern):
            return True
    return False


def requested_primary_artifact_types(content: str) -> set[str]:
    lowered = content.lower()
    if _has_positive_requested_artifact(lowered, r"(pptx?|幻灯片|演示文稿)"):
        return {"ppt_deck"}
    if _has_positive_requested_artifact(lowered, r"(html|网页|页面)"):
        return {"html_page"}
    if _has_positive_requested_artifact(lowered, r"(图片|图像|生图|image|png|jpe?g)"):
        return {"image_result"}
    if _has_positive_requested_artifact(lowered, r"(csv|excel|xlsx|数据表文件|表格文件)"):
        return {"data_table"}
    if _has_positive_requested_artifact(lowered, r"(markdown|\.md\b|md 文件|md文件)"):
        return {"markdown_report"}
    return set()


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
    lowered = diagnostic_text.lower()
    if not any(marker in lowered for marker in FATAL_RUNTIME_MARKERS):
        return
    tail = diagnostic_text.strip()[-800:] or "Agent runtime reported a model/API failure."
    raise RuntimeError(f"Agent runtime reported a model/API failure: {tail}")


def _is_placeholder_output(assistant_output: str) -> bool:
    normalized = " ".join((assistant_output or "").strip().lower().split())
    return not normalized or normalized in PLACEHOLDER_OUTPUTS


async def session_source_artifact_paths(
    db: AsyncSession,
    conversation_id: str,
    run_id: str,
    artifact_types: set[str],
) -> list[str]:
    if not artifact_types:
        return []
    result = await db.execute(
        select(Artifact)
        .where(
            Artifact.conversation_id == conversation_id,
            Artifact.run_id != run_id,
            Artifact.type.in_(artifact_types),
            Artifact.is_primary.is_(True),
        )
        .order_by(Artifact.created_at.desc())
        .limit(8)
    )
    paths: list[str] = []
    for artifact in result.scalars().all():
        metadata = artifact.artifact_metadata or {}
        for key in ("originalPath", "path"):
            value = metadata.get(key)
            if isinstance(value, str) and value and value not in paths:
                paths.append(value)
    return paths


def source_artifact_types_for_request(
    requested_artifact_types: set[str],
    skill_key: str | None,
) -> set[str]:
    source_types: set[str] = set()
    if "html_page" in requested_artifact_types or skill_key == "html_generation":
        source_types.add("markdown_report")
    if "ppt_deck" in requested_artifact_types or skill_key == "ppt_generation":
        source_types.update({"markdown_report", "html_page"})
    return source_types


def required_primary_artifact_types(
    skill_key: str | None,
    content: str,
    requested_artifact_types: set[str] | None = None,
) -> set[str]:
    required_types = set(PRIMARY_ARTIFACT_TYPES_BY_SKILL.get(skill_key or "", set()))
    required_types.update(
        requested_primary_artifact_types(content)
        if requested_artifact_types is None
        else requested_artifact_types
    )
    return required_types


def _artifact_metadata(artifact) -> dict:
    metadata = getattr(artifact, "artifact_metadata", None)
    if metadata is None:
        metadata = getattr(artifact, "metadata", None)
    return metadata or {}


def _artifact_is_debug(artifact) -> bool:
    metadata = _artifact_metadata(artifact)
    return (
        getattr(artifact, "type", None) == "debug_json"
        or metadata.get("developerOnly") is True
        or metadata.get("artifactRole") == "intermediate"
        or (
            getattr(artifact, "is_primary", True) is False
            and metadata.get("artifactRole") == "preview_fallback"
        )
    )


def has_required_primary_artifact(
    artifacts,
    required_types: set[str],
) -> bool:
    if not required_types:
        return bool(artifacts)
    return any(
        artifact.type in required_types and not _artifact_is_debug(artifact)
        for artifact in artifacts
    )


def delayed_discovery_attempts(required_types: set[str]) -> int:
    return max(
        (
            DELAYED_DISCOVERY_ATTEMPTS_BY_TYPE.get(artifact_type, 0)
            for artifact_type in required_types
        ),
        default=0,
    )


async def delayed_discover_primary_artifacts(
    session_id: str,
    since: datetime,
    explicit_artifact_paths: list[str],
    source_path_candidates: list[str],
    run_id: str,
    explicit_artifacts: list[object],
    required_types: set[str],
) -> list[schemas.Artifact]:
    attempts = delayed_discovery_attempts(required_types)
    discovered_artifacts: list[schemas.Artifact] = []
    for attempt in range(attempts):
        await asyncio.sleep(DELAYED_DISCOVERY_INTERVAL_SECONDS)
        related_source_artifact_paths = await asyncio.to_thread(
            discover_related_artifact_paths,
            source_path_candidates,
            since,
        )
        for path in related_source_artifact_paths:
            if path not in explicit_artifact_paths:
                explicit_artifact_paths.append(path)
        discovered_artifacts = await discover_artifacts_with_retry(
            session_id,
            since,
            explicit_artifact_paths,
            run_id,
            explicit_artifacts,
        )
        if not has_required_primary_artifact(discovered_artifacts, required_types):
            discovered_artifacts.extend(
                await asyncio.to_thread(
                    discover_artifacts_since,
                    session_id,
                    since,
                    run_id,
                )
            )
        if has_required_primary_artifact(discovered_artifacts, required_types):
            return discovered_artifacts
        if attempt == attempts - 1:
            return discovered_artifacts
    return discovered_artifacts


async def discover_and_persist_run_artifacts(
    db: AsyncSession,
    run: AgentRun,
    conversation_id: str,
    skill_key: str | None,
    run_started_at: datetime,
    adapter: object,
    artifact_discovery_summary: dict[str, object],
    user_id: str,
    content: str = "",
    assistant_output: str = "",
):
    run_id_value = run.id
    explicit_artifact_paths = (
        adapter.get_last_artifact_paths() if hasattr(adapter, "get_last_artifact_paths") else []
    )
    explicit_artifacts = (
        adapter.get_last_artifacts() if hasattr(adapter, "get_last_artifacts") else []
    )
    if explicit_artifacts:
        explicit_artifact_paths = [
            str(getattr(artifact, "path", ""))
            for artifact in explicit_artifacts
            if getattr(artifact, "path", "")
        ]
    event_path_candidates: list[str] = []
    result = await db.execute(select(AgentRunEvent).where(AgentRunEvent.run_id == run_id_value))
    for event in result.scalars().all():
        event_path_candidates.extend(extract_artifact_path_strings(event.payload or {}))
    for path in event_path_candidates:
        if path not in explicit_artifact_paths:
            explicit_artifact_paths.append(path)
    source_path_candidates = extract_artifact_path_strings(content)
    source_path_candidates.extend(
        path
        for path in extract_artifact_path_strings(assistant_output)
        if path not in source_path_candidates
    )
    requested_artifact_types = requested_primary_artifact_types(content)
    source_artifact_types = source_artifact_types_for_request(requested_artifact_types, skill_key)
    if source_artifact_types:
        for path in await session_source_artifact_paths(
            db,
            conversation_id,
            run_id_value,
            source_artifact_types,
        ):
            if path not in source_path_candidates:
                source_path_candidates.append(path)

    related_source_artifact_paths = discover_related_artifact_paths(
        source_path_candidates,
        run_started_at,
    )
    for path in related_source_artifact_paths:
        if path not in explicit_artifact_paths:
            explicit_artifact_paths.append(path)
    artifact_discovery_summary.update(
        {
            "adapter_artifact_paths": list(explicit_artifact_paths),
            "source_artifact_paths": source_path_candidates,
            "related_source_artifact_paths": related_source_artifact_paths,
            "adapter_artifacts": [
                {
                    "artifact_path": getattr(artifact, "path", None),
                    "artifact_type": getattr(artifact, "artifact_type", None),
                    "run_id": getattr(artifact, "run_id", None),
                    "source_dir": getattr(artifact, "source_dir", None),
                    "title": getattr(artifact, "title", None),
                }
                for artifact in explicit_artifacts
            ],
        }
    )
    discovered_artifacts = await discover_artifacts_with_retry(
        conversation_id,
        run_started_at,
        explicit_artifact_paths,
        run_id_value,
        explicit_artifacts,
    )
    required_types = required_primary_artifact_types(
        skill_key,
        content,
        requested_artifact_types,
    )
    if required_types and not has_required_primary_artifact(discovered_artifacts, required_types):
        delayed_artifacts = await delayed_discover_primary_artifacts(
            conversation_id,
            run_started_at,
            explicit_artifact_paths,
            source_path_candidates,
            run_id_value,
            explicit_artifacts,
            required_types,
        )
        if delayed_artifacts:
            discovered_artifacts = delayed_artifacts
            artifact_discovery_summary["delayed_retry_count"] = delayed_discovery_attempts(
                required_types
            )
            artifact_discovery_summary["delayed_artifact_paths"] = [
                str(_artifact_metadata(artifact).get("path") or "")
                for artifact in discovered_artifacts
            ]
    if (
        skill_key == "ppt_generation"
        and any(artifact.type == "html_page" for artifact in discovered_artifacts)
        and not any(artifact.type == "ppt_deck" for artifact in discovered_artifacts)
    ):
        try:
            pptx_artifact = await asyncio.to_thread(
                create_pptx_from_html_artifacts,
                conversation_id,
                discovered_artifacts,
                run_id_value,
                settings.agent_run_ppt_export_timeout_seconds,
            )
            if pptx_artifact is not None:
                discovered_artifacts.append(pptx_artifact)
        except subprocess.TimeoutExpired as error:
            raise AgentRunTimeout(
                "ppt_export_timeout",
                f"PPTX export exceeded {settings.agent_run_ppt_export_timeout_seconds} seconds.",
            ) from error

    stored_artifacts = await persist_discovered_artifacts(
        db,
        conversation_id,
        discovered_artifacts,
        run_id_value,
    )
    current_run_artifacts = [
        artifact for artifact in stored_artifacts if artifact.run_id == run_id_value
    ]
    should_create_markdown_fallback = (
        "markdown_report" in requested_artifact_types
        or skill_key in {"data_analysis", "deep_research"}
    )
    if (
        not current_run_artifacts
        and assistant_output
        and not _is_placeholder_output(assistant_output)
        and should_create_markdown_fallback
    ):
        fallback_artifact = create_markdown_artifact_from_content(
            conversation_id,
            assistant_output,
            run_id_value,
        )
        if fallback_artifact is not None:
            stored_artifacts.extend(
                await persist_discovered_artifacts(
                    db,
                    conversation_id,
                    [fallback_artifact],
                    run_id_value,
                )
            )
            current_run_artifacts = [
                artifact for artifact in stored_artifacts if artifact.run_id == run_id_value
            ]
    should_create_html_fallback = "html_page" in requested_artifact_types
    if (
        not current_run_artifacts
        and assistant_output
        and not _is_placeholder_output(assistant_output)
        and should_create_html_fallback
    ):
        fallback_artifact = create_html_artifact_from_content(
            conversation_id,
            assistant_output,
            run_id_value,
        )
        if fallback_artifact is not None:
            stored_artifacts.extend(
                await persist_discovered_artifacts(
                    db,
                    conversation_id,
                    [fallback_artifact],
                    run_id_value,
                )
            )
            current_run_artifacts = [
                artifact for artifact in stored_artifacts if artifact.run_id == run_id_value
            ]
    should_create_ppt_fallback = (
        "ppt_deck" in requested_artifact_types or skill_key == "ppt_generation"
    )
    if should_create_ppt_fallback and not any(
        artifact.type == "ppt_deck" for artifact in current_run_artifacts
    ):
        html_candidates = [
            artifact for artifact in current_run_artifacts if artifact.type == "html_page"
        ]
        if not html_candidates:
            html_candidates = await latest_session_html_artifacts(db, conversation_id)
        if html_candidates:
            try:
                pptx_artifact = await asyncio.to_thread(
                    create_pptx_from_html_artifacts,
                    conversation_id,
                    html_candidates,
                    run_id_value,
                    settings.agent_run_ppt_export_timeout_seconds,
                )
                if pptx_artifact is not None:
                    stored_artifacts.extend(
                        await persist_discovered_artifacts(
                            db,
                            conversation_id,
                            [pptx_artifact],
                            run_id_value,
                        )
                    )
                    current_run_artifacts = [
                        artifact
                        for artifact in stored_artifacts
                        if artifact.run_id == run_id_value
                    ]
            except subprocess.TimeoutExpired as error:
                raise AgentRunTimeout(
                    "ppt_export_timeout",
                    (
                        "PPTX export from existing HTML exceeded "
                        f"{settings.agent_run_ppt_export_timeout_seconds} seconds."
                    ),
                ) from error
    if not current_run_artifacts:
        raise_for_fatal_runtime_diagnostics(adapter, assistant_output or "")
    validate_primary_artifacts(skill_key, current_run_artifacts, content, requested_artifact_types)
    developer_mode = await user_developer_mode_by_id(db, user_id)
    visible_current_run_artifacts = [
        artifact
        for artifact in current_run_artifacts
        if developer_mode or not is_debug_artifact(artifact)
    ]
    visible_stored_artifacts = [
        artifact
        for artifact in stored_artifacts
        if developer_mode or not is_debug_artifact(artifact)
    ]
    response_artifacts = (
        visible_current_run_artifacts
        or sorted(
            visible_stored_artifacts,
            key=artifact_display_priority,
        )[-1:]
    )
    artifact_discovery_summary["stored_count"] = len(stored_artifacts)
    return response_artifacts


def validate_primary_artifacts(
    skill_key: str | None,
    current_run_artifacts,
    content: str = "",
    requested_artifact_types: set[str] | None = None,
) -> None:
    primary_candidates = [
        artifact for artifact in current_run_artifacts if not is_debug_artifact(artifact)
    ]
    required_primary_types = required_primary_artifact_types(
        skill_key,
        content,
        requested_artifact_types,
    )
    if required_primary_types and not any(
        artifact.type in required_primary_types for artifact in primary_candidates
    ):
        expected = ", ".join(sorted(required_primary_types))
        raise RuntimeError(
            f"{skill_key} completed without producing a primary artifact ({expected})."
        )
    if skill_key == "ppt_generation" and not primary_candidates:
        raise RuntimeError("PPT generation completed without producing any artifact.")
    if (
        skill_key == "ppt_generation"
        and any(artifact.type == "html_page" for artifact in primary_candidates)
        and not any(artifact.type == "ppt_deck" for artifact in primary_candidates)
    ):
        raise RuntimeError(
            "PPTX export did not produce a .pptx file. "
            "HTML pages were preserved as fallback artifacts."
        )


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
            "Agent runtime completed and generated artifacts."
            if response_artifacts
            else "Agent runtime completed without emitting a visible status update."
        ),
        [artifact.id for artifact in response_artifacts] or None,
    )


async def latest_session_html_artifacts(
    db: AsyncSession,
    conversation_id: str,
    limit: int = 20,
):
    result = await db.execute(
        select(Artifact)
        .where(
            Artifact.conversation_id == conversation_id,
            Artifact.type == "html_page",
            Artifact.is_primary.is_(True),
        )
        .order_by(Artifact.created_at.desc())
        .limit(limit)
    )
    return [to_artifact(artifact) for artifact in result.scalars().all()]


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
    return to_interface_schema(user_settings).developer_mode
