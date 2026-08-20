# File purpose: Implements the agent run control backend service workflow.
# Main declarations: AgentRunCancelled defines agent run cancelled state or behavior;
# AgentRunTimeout defines agent run timeout state or behavior; AgentRunCancellationPoller limits
# repeated database reads; is_agent_run_cancelled checks agent run cancelled.

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun


class AgentRunCancelled(Exception):
    pass


class AgentRunTimeout(Exception):
    def __init__(self, timeout_type: str, message: str) -> None:
        self.timeout_type = timeout_type
        super().__init__(message)


class AgentRunCancellationPoller:
    """Caches negative cancellation reads briefly while preserving terminal checks."""

    def __init__(self, interval_seconds: float = 0.5) -> None:
        self.interval_seconds = max(0.0, interval_seconds)
        self._cancelled = False
        self._next_check_at = 0.0

    async def is_cancelled(
        self,
        db: AsyncSession,
        run_id: str,
        *,
        force: bool = False,
    ) -> bool:
        if self._cancelled:
            return True
        now = time.monotonic()
        if not force and now < self._next_check_at:
            return False
        self._cancelled = await is_agent_run_cancelled(db, run_id)
        self._next_check_at = now + self.interval_seconds
        return self._cancelled


async def is_agent_run_cancelled(db: AsyncSession, run_id: str) -> bool:
    result = await db.execute(select(AgentRun.status).where(AgentRun.id == run_id))
    return result.scalar_one_or_none() == "cancelled"
