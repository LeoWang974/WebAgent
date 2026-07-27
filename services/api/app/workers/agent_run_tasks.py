import asyncio

from app.services.agent_run_executor import execute_queued_agent_run
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.agent_run_tasks.execute_agent_run_task")
def execute_agent_run_task(run_id: str) -> None:
    asyncio.run(execute_queued_agent_run(run_id))
