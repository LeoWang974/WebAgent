import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from ..schemas import AgentArtifactRef, AgentRun, AgentRunCreate, AgentRunEvent, AgentRunStep
from .base import AgentRuntimeAdapter
from .hermes_cli import HermesCliWrapper


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class HermesAdapter(AgentRuntimeAdapter):
    def __init__(
        self,
        hermes_path: str = "hermes",
        hermes_home: str = "~/.hermes",
        wsl_distribution: str = "Ubuntu",
    ):
        self.cli = HermesCliWrapper(hermes_path, hermes_home, wsl_distribution)

    async def create_run(self, input_data: AgentRunCreate) -> AgentRun:
        try:
            toolsets = self._get_toolsets_for_skill(input_data.skill_key)
            skills = self._get_skills_for_skill(input_data.skill_key)
            question = self._build_runtime_prompt(input_data.content, input_data.skill_key)

            session_id, response = await self.cli.ask(
                question=question,
                toolsets=toolsets,
                skills=skills,
            )

            run_id = (
                f"run_hermes_{session_id}"
                if session_id
                else f"run_hermes_{input_data.session_id}"
            )
            run = AgentRun(
                id=run_id,
                session_id=input_data.session_id,
                status="completed",
                title="Hermes Agent Run",
                progress=100,
                steps=[
                    AgentRunStep(
                        id=f"step_{session_id}_1",
                        label="Completed",
                        status="completed",
                        timestamp=now_iso(),
                    )
                ],
                started_at=now_iso(),
                completed_at=now_iso(),
                output=response,
            )

            return run

        except Exception as e:
            return AgentRun(
                id=f"run_hermes_{input_data.session_id}",
                session_id=input_data.session_id,
                status="failed",
                title="Hermes Agent Run",
                progress=0,
                steps=[],
                started_at=now_iso(),
                error=str(e),
            )

    async def get_run(self, run_id: str) -> AgentRun:
        return AgentRun(
            id=run_id,
            session_id="",
            status="completed",
            title="Hermes Agent Run",
            progress=100,
            steps=[],
            started_at=now_iso(),
            completed_at=now_iso(),
        )

    async def cancel_run(self, run_id: str) -> AgentRun:
        await self.cli.cancel_run(run_id)
        return AgentRun(
            id=run_id,
            session_id="",
            status="cancelled",
            title="Hermes Agent Run",
            progress=0,
            steps=[],
            started_at=now_iso(),
            completed_at=now_iso(),
        )

    async def stream_events(
        self, run_id: str
    ) -> AsyncGenerator[AgentRunEvent, None]:
        yield AgentRunEvent(
            run_id=run_id,
            status="queued",
            progress=10,
            completed_at=None,
            step=AgentRunStep(
                id=f"{run_id}_step_1",
                label="Initializing Hermes Agent",
                status="running",
                timestamp=now_iso(),
            ),
        )

        await asyncio.sleep(0.5)

        yield AgentRunEvent(
            run_id=run_id,
            status="running",
            progress=30,
            completed_at=None,
            step=AgentRunStep(
                id=f"{run_id}_step_2",
                label="Processing request",
                status="running",
                timestamp=now_iso(),
            ),
        )

        await asyncio.sleep(0.5)

        yield AgentRunEvent(
            run_id=run_id,
            status="tool_calling",
            progress=60,
            completed_at=None,
            step=AgentRunStep(
                id=f"{run_id}_step_3",
                label="Executing tools",
                status="running",
                timestamp=now_iso(),
            ),
        )

        await asyncio.sleep(0.5)

        yield AgentRunEvent(
            run_id=run_id,
            status="rendering",
            progress=85,
            completed_at=None,
            step=AgentRunStep(
                id=f"{run_id}_step_4",
                label="Generating response",
                status="running",
                timestamp=now_iso(),
            ),
        )

        await asyncio.sleep(0.5)

        yield AgentRunEvent(
            run_id=run_id,
            status="completed",
            progress=100,
            completed_at=now_iso(),
            step=AgentRunStep(
                id=f"{run_id}_step_5",
                label="Completed",
                status="completed",
                timestamp=now_iso(),
            ),
            output="Hermes agent run completed successfully.",
        )

    async def stream_response(
        self,
        input_data: AgentRunCreate,
    ) -> AsyncGenerator[str, None]:
        async for event in self.stream_response_events(input_data):
            if event.step and event.step.label:
                yield event.step.label

    async def stream_response_events(
        self,
        input_data: AgentRunCreate,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        toolsets = self._get_toolsets_for_skill(input_data.skill_key)
        skills = self._get_skills_for_skill(input_data.skill_key)
        question = self._build_runtime_prompt(input_data.content, input_data.skill_key)
        event_index = 0

        async for event in self.cli.ask_stream_events(
            question=question,
            run_id=input_data.run_id,
            toolsets=toolsets,
            skills=skills,
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

    def _get_toolsets_for_skill(self, skill_key: str | None) -> str | None:
        toolsets_map = {
            "data_analysis": "file,terminal,web",
            "deep_research": "web,terminal,file",
            "ppt_generation": "file,web",
            "u1_image": "image_gen,web,terminal,file",
        }
        return toolsets_map.get(skill_key)

    def _get_skills_for_skill(self, skill_key: str | None) -> str | None:
        skills_map = {
            "data_analysis": "sn-da-excel-workflow",
            "deep_research": "sn-deep-research",
            "ppt_generation": "sn-ppt-workbench",
            "u1_image": "sn-image-base",
        }
        return skills_map.get(skill_key)

    @staticmethod
    def _build_runtime_prompt(content: str, skill_key: str | None) -> str:
        return content
