import asyncio

from app.db.session import engine
from app.services.agent_run_executor import execute_queued_agent_run
from app.workers.celery_app import celery_app


async def _execute_agent_run_task(run_id: str) -> None:
    try:
        await execute_queued_agent_run(run_id)
    finally:
        await engine.dispose()


@celery_app.task(name="app.workers.agent_run_tasks.execute_agent_run_task")
def execute_agent_run_task(run_id: str) -> None:
    asyncio.run(_execute_agent_run_task(run_id))
