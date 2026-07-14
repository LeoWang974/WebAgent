import asyncio
from datetime import UTC, datetime
from typing import AsyncGenerator, Optional

from ..schemas import AgentRun, AgentRunCreate, AgentRunEvent, AgentRunStep
from .base import AgentRuntimeAdapter
from .hermes_cli import HermesCliWrapper


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class HermesAdapter(AgentRuntimeAdapter):
    def __init__(
        self,
        hermes_path: str = "/home/zhuchangbiaozhu_xyl/.local/bin/hermes",
        hermes_home: str = "/home/zhuchangbiaozhu_xyl/.hermes",
        wsl_distribution: str = "Ubuntu",
    ):
        self.cli = HermesCliWrapper(hermes_path, hermes_home, wsl_distribution)

    async def create_run(self, input_data: AgentRunCreate) -> AgentRun:
        try:
            toolsets = self._get_toolsets_for_skill(input_data.skill_key)
            skills = self._get_skills_for_skill(input_data.skill_key)

            session_id, response = await self.cli.ask(
                question=input_data.content,
                toolsets=toolsets,
                skills=skills,
            )

            run = AgentRun(
                id=f"run_hermes_{session_id}" if session_id else f"run_hermes_{input_data.session_id}",
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
        toolsets = self._get_toolsets_for_skill(input_data.skill_key)
        skills = self._get_skills_for_skill(input_data.skill_key)

        async for response in self.cli.ask_stream(
            question=input_data.content,
            run_id=input_data.run_id,
            toolsets=toolsets,
            skills=skills,
        ):
            if response:
                yield response

    def get_last_artifact_paths(self) -> list[str]:
        return list(self.cli.last_artifact_paths)

    def _get_toolsets_for_skill(self, skill_key: Optional[str]) -> Optional[str]:
        toolsets_map = {
            "data_analysis": "file,terminal,web",
            "deep_research": "web,terminal,file",
            "ppt_generation": "file,web",
            "u1_image": "image_gen,web",
        }
        return toolsets_map.get(skill_key)

    def _get_skills_for_skill(self, skill_key: Optional[str]) -> Optional[str]:
        skills_map = {
            "data_analysis": "sn-da-excel-workflow",
            "deep_research": "sn-research-report",
            "ppt_generation": "sn-ppt-entry",
            "u1_image": "sn-image-base",
        }
        return skills_map.get(skill_key)
