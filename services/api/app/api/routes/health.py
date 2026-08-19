# File purpose: Defines FastAPI endpoints for the health API surface.
# Main declarations: _check_postgresql handles check postgresql; _check_redis handles check redis;
# health_check handles health check.

import asyncio
import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

router = APIRouter()
logger = logging.getLogger(__name__)

DEPENDENCY_CHECK_TIMEOUT_SECONDS = 3.0


async def _check_postgresql() -> bool:
    async def ping() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(ping(), timeout=DEPENDENCY_CHECK_TIMEOUT_SECONDS)
    except Exception:
        logger.warning("PostgreSQL health check failed", exc_info=True)
        return False
    return True


async def _check_redis() -> bool:
    client: Redis | None = None
    try:
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=DEPENDENCY_CHECK_TIMEOUT_SECONDS,
            socket_timeout=DEPENDENCY_CHECK_TIMEOUT_SECONDS,
        )
        return bool(
            await asyncio.wait_for(
                client.ping(),
                timeout=DEPENDENCY_CHECK_TIMEOUT_SECONDS,
            )
        )
    except Exception:
        logger.warning("Redis health check failed", exc_info=True)
        return False
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                logger.debug("Redis health client close failed", exc_info=True)


@router.get("/health")
async def health_check() -> JSONResponse:
    postgresql_ok, redis_ok = await asyncio.gather(
        _check_postgresql(),
        _check_redis(),
    )
    checks = {
        "postgresql": "ok" if postgresql_ok else "unavailable",
        "redis": "ok" if redis_ok else "unavailable",
    }
    healthy = postgresql_ok and redis_ok
    return JSONResponse(
        content={
            "status": "ok" if healthy else "unavailable",
            "checks": checks,
        },
        status_code=status.HTTP_200_OK
        if healthy
        else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
