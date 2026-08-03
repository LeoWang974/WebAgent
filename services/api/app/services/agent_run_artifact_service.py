import subprocess
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.settings import DEFAULT_INTERFACE, to_interface_schema
from app.core.config import settings
from app.models import AgentRun, AgentRunEvent, Message, UserSettings
from app.services.agent_run_control import AgentRunTimeout
from app.services.artifact_discovery import (
    create_markdown_artifact_from_content,
    create_pptx_from_html_artifacts,
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


def _has_positive_token(text: str, tokens: tuple[str, ...]) -> bool:
    negative_markers = ("不", "不要", "不得", "无需", "不是", "非", "no ", "not ", "without ")
    for token in tokens:
        start = 0
        while True:
            index = text.find(token, start)
            if index < 0:
                break
            prefix = text[max(0, index - 16) : index]
            if not any(marker in prefix for marker in negative_markers):
                return True
            start = index + len(token)
    return False


def requested_primary_artifact_types(content: str) -> set[str]:
    lowered = content.lower()
    if _has_positive_token(lowered, ("ppt", "pptx", "幻灯片", "演示文稿")):
        return {"ppt_deck"}
    if _has_positive_token(lowered, ("html", "网页", "页面")):
        return {"html_page"}
    if _has_positive_token(lowered, ("图片", "图像", "生图", "image", "png", "jpg", "jpeg")):
        return {"image_result"}
    if _has_positive_token(lowered, ("csv", "excel", "xlsx", "数据表文件", "表格文件")):
        return {"data_table"}
    if _has_positive_token(lowered, ("markdown", ".md", " md", "md文件", "md 文件")):
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
    if (
        skill_key == "ppt_generation"
        and any(artifact.type == "html_page" for artifact in discovered_artifacts)
        and not any(artifact.type == "ppt_deck" for artifact in discovered_artifacts)
    ):
        try:
            pptx_artifact = create_pptx_from_html_artifacts(
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
    requested_artifact_types = requested_primary_artifact_types(content)
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
    required_primary_types = set(PRIMARY_ARTIFACT_TYPES_BY_SKILL.get(skill_key or "", set()))
    required_primary_types.update(
        requested_primary_artifact_types(content)
        if requested_artifact_types is None
        else requested_artifact_types
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
