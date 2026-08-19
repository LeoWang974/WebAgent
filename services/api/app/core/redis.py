# File purpose: Provides core redis configuration and infrastructure helpers.
# Main declarations: this file contains declarative configuration or re-exports and has no
# callable declarations.

from redis.asyncio import Redis

from app.core.config import settings

redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
