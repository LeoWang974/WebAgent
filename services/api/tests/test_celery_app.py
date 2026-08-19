# File purpose: Verifies test celery app behavior and its regression contracts.
# Main declarations: test_agent_workers_only_prefetch_one_long_run verifies agent workers only
# prefetch one long run.

from app.workers.celery_app import celery_app


def test_agent_workers_only_prefetch_one_long_run() -> None:
    assert celery_app.conf.worker_prefetch_multiplier == 1
