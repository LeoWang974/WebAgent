from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from ..schemas import AgentArtifactRef, AgentRunCreate, AgentRunEvent, AgentRunStep
from .hermes_cli import HermesCliWrapper


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class HermesAdapter:
    def __init__(
        self,
        hermes_path: str = "hermes",
        hermes_home: str = "~/.hermes",
        wsl_distribution: str = "Ubuntu",
        serper_configured: bool = False,
    ):
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

        async for event in self.cli.ask_stream_events(
            question=input_data.content,
            run_id=input_data.run_id,
            working_dir=input_data.working_dir,
            artifacts_dir=input_data.artifacts_dir,
        ):
            if hasattr(event, "content"):
                content = str(event.content or "").strip()
                event_type = str(getattr(event, "event_type", "stage_update") or "stage_update")
                payload = event.to_payload() if hasattr(event, "to_payload") else {}
            else:
                content = str(event.get("content") or "").strip()
                event_type = str(event.get("event_type") or "stage_update")
                payload = dict(event.get("payload") or {})
            if not content:
                continue
            event_index += 1
            yield AgentRunEvent(
                run_id=input_data.run_id or input_data.session_id,
                event_type=event_type,
                status="running",
                progress=min(90, 10 + event_index * 8),
                payload=payload,
                step=AgentRunStep(
                    id=f"{input_data.run_id or input_data.session_id}_stage_{event_index}",
                    label=content,
                    status="completed",
                    timestamp=now_iso(),
                ),
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
            )
            for item in self.cli.last_artifacts
            if item.get("artifact_path")
        ]

    def get_last_diagnostics(self) -> dict[str, object]:
        return dict(self.cli.last_diagnostics)
