from app.workers.celery_app import celery_app


@celery_app.task(name="agent_runs.mock_run")
def mock_agent_run(run_id: str) -> dict[str, str]:
    return {"run_id": run_id, "status": "completed"}
