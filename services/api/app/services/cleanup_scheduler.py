# File purpose: Implements the cleanup scheduler backend service workflow.
# Main declarations: run_configured_data_cleanup runs configured data cleanup;
# run_periodic_data_cleanup runs periodic data cleanup; stop_cleanup_task stops cleanup task.

import asyncio
import logging
from contextlib import suppress

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.cleanup import CleanupResult, run_data_cleanup

logger = logging.getLogger(__name__)


async def run_configured_data_cleanup() -> CleanupResult:
    async with AsyncSessionLocal() as db:
        result = await run_data_cleanup(
            db,
            disconnected_run_max_age_days=settings.cleanup_disconnected_run_max_age_days,
            runtime_file_max_age_days=settings.cleanup_runtime_file_max_age_days,
        )
    logger.info("Data cleanup finished: %s", result)
    return result


async def run_periodic_data_cleanup() -> None:
    if settings.cleanup_initial_delay_seconds > 0:
        await asyncio.sleep(settings.cleanup_initial_delay_seconds)

    while True:
        try:
            await run_configured_data_cleanup()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Data cleanup failed")
        await asyncio.sleep(settings.cleanup_interval_seconds)


async def stop_cleanup_task(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
