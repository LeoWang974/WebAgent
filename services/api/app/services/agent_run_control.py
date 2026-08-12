from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun


class AgentRunCancelled(Exception):
    pass


class AgentRunTimeout(Exception):
    def __init__(self, timeout_type: str, message: str) -> None:
        self.timeout_type = timeout_type
        super().__init__(message)


async def is_agent_run_cancelled(db: AsyncSession, run_id: str) -> bool:
    result = await db.execute(select(AgentRun.status).where(AgentRun.id == run_id))
    return result.scalar_one_or_none() == "cancelled"
