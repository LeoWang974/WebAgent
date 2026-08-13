from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "webagent",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    imports=("app.workers.agent_run_tasks",),
    result_serializer="json",
    timezone="UTC",
    task_default_queue=settings.agent_run_queue_name,
    # Long-running agent jobs must remain visible to idle workers. Celery's
    # default prefetch can otherwise let one solo worker reserve several runs
    # while newly started workers sit idle.
    worker_prefetch_multiplier=1,
)
