import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun

logger = logging.getLogger(__name__)


class AgentRunCancelled(Exception):
    pass


class AgentRunTimeout(Exception):
    def __init__(self, timeout_type: str, message: str) -> None:
        self.timeout_type = timeout_type
        super().__init__(message)


async def is_agent_run_cancelled(db: AsyncSession, run_id: str) -> bool:
    result = await db.execute(select(AgentRun.status).where(AgentRun.id == run_id))
    return result.scalar_one_or_none() == "cancelled"


async def cancel_adapter_run_safely(adapter: object | None, run_id: str) -> bool:
    cancel_run = getattr(adapter, "cancel_run", None)
    if not callable(cancel_run):
        return False
    try:
        await cancel_run(run_id)
    except Exception as error:
        logger.warning("Failed to cancel adapter run %s: %s", run_id, error)
        return False
    return True
