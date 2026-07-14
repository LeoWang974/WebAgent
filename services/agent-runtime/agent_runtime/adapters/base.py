from abc import ABC, abstractmethod
from typing import AsyncGenerator

from ..schemas import AgentRun, AgentRunCreate, AgentRunEvent


class AgentRuntimeAdapter(ABC):
    @abstractmethod
    async def create_run(self, input_data: AgentRunCreate) -> AgentRun:
        pass

    @abstractmethod
    async def get_run(self, run_id: str) -> AgentRun:
        pass

    @abstractmethod
    async def cancel_run(self, run_id: str) -> AgentRun:
        pass

    @abstractmethod
    async def stream_events(
        self, run_id: str
    ) -> AsyncGenerator[AgentRunEvent, None]:
        pass

    async def stream_response(
        self, input_data: AgentRunCreate
    ) -> AsyncGenerator[str, None]:
        run = await self.create_run(input_data)
        if getattr(run, "output", None):
            yield run.output
