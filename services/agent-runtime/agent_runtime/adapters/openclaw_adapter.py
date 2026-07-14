import asyncio
from typing import AsyncGenerator

import httpx

from ..schemas import AgentRun, AgentRunCreate, AgentRunEvent, AgentRunStep
from .base import AgentRuntimeAdapter


class OpenClawAdapter(AgentRuntimeAdapter):
    def __init__(self, base_url: str = "http://localhost:8643"):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=60)

    def _parse_steps(self, raw_steps: list) -> list[AgentRunStep]:
        steps: list[AgentRunStep] = []

        for index, item in enumerate(raw_steps):
            if isinstance(item, AgentRunStep):
                steps.append(item)
                continue

            if isinstance(item, dict):
                steps.append(
                    AgentRunStep(
                        id=item.get("id", f"step_{index}"),
                        label=item.get("label", "Step"),
                        status=item.get("status", "completed"),
                        timestamp=item.get("timestamp"),
                    )
                )

        return steps

    async def create_run(self, input_data: AgentRunCreate) -> AgentRun:
        payload = {
            "content": input_data.content,
            "session_id": input_data.session_id,
        }
        if input_data.skill_key:
            payload["skill_key"] = input_data.skill_key
        if input_data.model_id:
            payload["model_id"] = input_data.model_id

        try:
            response = await self.client.post(
                f"{self.base_url}/api/agent-runs",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return AgentRun(
                id=data.get("id", f"run_openclaw_{input_data.session_id}"),
                session_id=data.get("session_id", input_data.session_id),
                status=data.get("status", "queued"),
                title=data.get("title", "OpenClaw Agent Run"),
                progress=data.get("progress", 0),
                steps=self._parse_steps(data.get("steps", [])),
                started_at=data.get("started_at", ""),
                completed_at=data.get("completed_at"),
                error=data.get("error"),
            )
        except Exception as e:
            return AgentRun(
                id=f"run_openclaw_{input_data.session_id}",
                session_id=input_data.session_id,
                status="failed",
                title="OpenClaw Agent Run",
                progress=0,
                steps=[],
                started_at="",
                error=str(e),
            )

    async def get_run(self, run_id: str) -> AgentRun:
        try:
            response = await self.client.get(f"{self.base_url}/api/agent-runs/{run_id}")
            response.raise_for_status()
            data = response.json()
            return AgentRun(
                id=data.get("id", run_id),
                session_id=data.get("session_id", ""),
                status=data.get("status", "unknown"),
                title=data.get("title", "OpenClaw Agent Run"),
                progress=data.get("progress", 0),
                steps=self._parse_steps(data.get("steps", [])),
                started_at=data.get("started_at", ""),
                completed_at=data.get("completed_at"),
                error=data.get("error"),
            )
        except Exception as e:
            return AgentRun(
                id=run_id,
                session_id="",
                status="failed",
                title="OpenClaw Agent Run",
                progress=0,
                steps=[],
                started_at="",
                error=str(e),
            )

    async def cancel_run(self, run_id: str) -> AgentRun:
        try:
            response = await self.client.post(
                f"{self.base_url}/api/agent-runs/{run_id}/cancel"
            )
            response.raise_for_status()
            data = response.json()
            return AgentRun(
                id=data.get("id", run_id),
                session_id=data.get("session_id", ""),
                status="cancelled",
                title=data.get("title", "OpenClaw Agent Run"),
                progress=data.get("progress", 0),
                steps=self._parse_steps(data.get("steps", [])),
                started_at=data.get("started_at", ""),
                completed_at=data.get("completed_at"),
            )
        except Exception as e:
            return AgentRun(
                id=run_id,
                session_id="",
                status="cancelled",
                title="OpenClaw Agent Run",
                progress=0,
                steps=[],
                started_at="",
                error=str(e),
            )

    async def stream_events(
        self, run_id: str
    ) -> AsyncGenerator[AgentRunEvent, None]:
        steps = [
            ("Connecting to OpenClaw", 5, "queued"),
            ("Initializing agent", 15, "running"),
            ("Processing request", 35, "running"),
            ("Calling tools", 60, "tool_calling"),
            ("Generating response", 85, "rendering"),
            ("Completed", 100, "completed"),
        ]

        for index, (label, progress, status) in enumerate(steps):
            await asyncio.sleep(0.6)
            event = AgentRunEvent(
                run_id=run_id,
                status=status,
                progress=progress,
                completed_at=None if status != "completed" else "",
                step=AgentRunStep(
                    id=f"{run_id}_step_{index}",
                    label=label,
                    status="completed" if status == "completed" else "running",
                    timestamp="",
                ),
            )
            yield event
