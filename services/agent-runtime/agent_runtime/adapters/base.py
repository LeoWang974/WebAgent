from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

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