# File purpose: Routes all Hermes requests to the shared worker queue without inspecting prompts.
# Main declarations: queue_for_message selects the Hermes queue; estimated_queue_position reads
# the current Redis queue length.

import logging

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

def queue_for_message() -> tuple[str, str]:
    """Return the shared Hermes queue without reading or classifying the prompt."""
    return settings.agent_run_queue_name, "Hermes 任务队列"


async def estimated_queue_position(queue_name: str) -> int | None:
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            return int(await redis.llen(queue_name)) + 1
        finally:
            await redis.aclose()
    except Exception as error:
        logger.debug("Could not estimate queue position for %s: %s", queue_name, error)
        return None
