from app.workers.celery_app import celery_app


def test_agent_workers_only_prefetch_one_long_run() -> None:
    assert celery_app.conf.worker_prefetch_multiplier == 1
