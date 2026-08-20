# File purpose: Implements the Hermes CLI integration for adapter.
# Main declarations: now_iso handles now iso; HermesAdapter defines hermes adapter state or
# behavior.

import re
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from .cli import HermesCliWrapper
from .schemas import AgentArtifactRef, AgentRunCreate, AgentRunEvent, AgentRunStep

RECOVERABLE_TOOL_STALL_MARKERS = (
    "stream stalled mid tool-call",
    "the action was not executed",
)
EXPLICIT_ARTIFACT_SUFFIX_RE = re.compile(
    r"\.(?:md|html?|pptx|png|jpe?g|csv|xlsx)\b",
    re.IGNORECASE,
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class HermesAdapter:
    def __init__(
        self,
        hermes_path: str = "hermes",
        hermes_home: str = "~/.hermes",
        wsl_distribution: str = "Ubuntu",
        serper_configured: bool = False,
        resume_session_id: str | None = None,
    ):
        self.resume_session_id = resume_session_id
        self.cli = HermesCliWrapper(
            hermes_path,
            hermes_home,
            wsl_distribution,
            serper_configured=serper_configured,
        )

    async def cancel_run(self, run_id: str) -> bool:
        return await self.cli.cancel_run(run_id)

    async def stream_response_events(
        self,
        input_data: AgentRunCreate,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        event_index = 0
        run_id = input_data.run_id or input_data.session_id
        requested_suffix = self._explicit_artifact_suffix(input_data.content)

        for attempt in range(2):
            recoverable_stall = False
            async for event in self.cli.ask_stream_events(
                question=input_data.content,
                session_id=self.resume_session_id if attempt == 0 else None,
                run_id=input_data.run_id,
                conversation_id=input_data.session_id,
                working_dir=input_data.working_dir,
                artifacts_dir=input_data.artifacts_dir,
            ):
                if hasattr(event, "content"):
                    content = str(event.content or "").strip()
                    event_type = str(
                        getattr(event, "event_type", "stage_update") or "stage_update"
                    )
                    payload = event.to_payload() if hasattr(event, "to_payload") else {}
                else:
                    content = str(event.get("content") or "").strip()
                    event_type = str(event.get("event_type") or "stage_update")
                    payload = dict(event.get("payload") or {})
                if not content:
                    continue
                if self._is_recoverable_tool_stall(content):
                    recoverable_stall = True
                    if attempt == 0 and not self.cli.last_artifact_paths:
                        continue
                event_index += 1
                yield AgentRunEvent(
                    run_id=run_id,
                    event_type=event_type,
                    status="running",
                    progress=min(90, 10 + event_index * 8),
                    payload=payload,
                    step=AgentRunStep(
                        id=f"{run_id}_stage_{event_index}",
                        label=content,
                        status="completed",
                        timestamp=now_iso(),
                    ),
                )

            diagnostics = self.cli.last_diagnostics or {}
            diagnostic_text = "\n".join(
                str(diagnostics.get(key) or "")
                for key in ("last_stage", "stdout_tail", "stderr_tail")
            )
            incomplete_handoff = self._is_incomplete_artifact_handoff(
                diagnostic_text,
                requested_suffix,
            )
            should_retry = (
                attempt == 0
                and not self.cli.last_artifact_paths
                and (recoverable_stall or incomplete_handoff)
            )
            if should_retry:
                event_index += 1
                yield AgentRunEvent(
                    run_id=run_id,
                    event_type="stage_started",
                    status="running",
                    progress=min(90, 10 + event_index * 8),
                    payload={
                        "protocol": "hermes.stream.v1",
                        "recoveryAttempt": 1,
                        "recoveryReason": (
                            "stalled_tool_call"
                            if recoverable_stall
                            else "incomplete_artifact_handoff"
                        ),
                    },
                    step=AgentRunStep(
                        id=f"{run_id}_stage_{event_index}",
                        label="Hermes 工具输出中断，正在使用干净会话重试一次...",
                        status="completed",
                        timestamp=now_iso(),
                    ),
                )
                continue
            break

    @staticmethod
    def _is_recoverable_tool_stall(content: str) -> bool:
        normalized = " ".join(content.lower().split())
        return all(marker in normalized for marker in RECOVERABLE_TOOL_STALL_MARKERS)

    @staticmethod
    def _explicit_artifact_suffix(content: str) -> str | None:
        matches = list(EXPLICIT_ARTIFACT_SUFFIX_RE.finditer(content))
        return matches[-1].group(0).lower() if matches else None

    @staticmethod
    def _is_incomplete_artifact_handoff(
        content: str,
        requested_suffix: str | None,
    ) -> bool:
        if not requested_suffix or requested_suffix not in content.lower():
            return False
        normalized = " ".join(content.lower().split())
        return (
            ("执行" in normalized and "即可生成" in normalized)
            or ("run " in normalized and "to generate" in normalized)
        )

    def get_last_artifact_paths(self) -> list[str]:
        return list(self.cli.last_artifact_paths)

    def get_last_artifacts(self) -> list[AgentArtifactRef]:
        return [
            AgentArtifactRef(
                path=str(item.get("artifact_path") or ""),
                artifact_type=(
                    str(item.get("artifact_type"))
                    if item.get("artifact_type") is not None
                    else None
                ),
                run_id=str(item.get("run_id")) if item.get("run_id") is not None else None,
                source_dir=(
                    str(item.get("source_dir"))
                    if item.get("source_dir") is not None
                    else None
                ),
                title=(str(item.get("title")) if item.get("title") is not None else None),
                entry_id=(
                    str(item.get("entry_id")) if item.get("entry_id") is not None else None
                ),
                role=str(item.get("role")) if item.get("role") is not None else None,
                status=str(item.get("status")) if item.get("status") is not None else None,
                discovered_by=(
                    str(item.get("discovered_by"))
                    if item.get("discovered_by") is not None
                    else None
                ),
                size_bytes=(
                    int(item.get("size_bytes"))
                    if isinstance(item.get("size_bytes"), int)
                    else None
                ),
                sha256=str(item.get("sha256")) if item.get("sha256") is not None else None,
                manifest_schema=(
                    str(item.get("manifest_schema"))
                    if item.get("manifest_schema") is not None
                    else None
                ),
            )
            for item in self.cli.last_artifacts
            if item.get("artifact_path")
        ]

    def get_last_diagnostics(self) -> dict[str, object]:
        return dict(self.cli.last_diagnostics)

    def get_last_artifact_manifest(self) -> dict[str, object] | None:
        recorder = self.cli.artifact_manifest_recorder
        return recorder.snapshot() if recorder is not None else None

    def get_last_artifact_manifest_path(self) -> str | None:
        recorder = self.cli.artifact_manifest_recorder
        return str(recorder.path) if recorder is not None else None
