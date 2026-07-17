import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.services.cleanup_scheduler import run_periodic_data_cleanup, stop_cleanup_task


logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cleanup_task: asyncio.Task[None] | None = None
    if settings.cleanup_enabled:
        cleanup_task = asyncio.create_task(run_periodic_data_cleanup())
        app.state.cleanup_task = cleanup_task
    try:
        yield
    finally:
        await stop_cleanup_task(cleanup_task)


def create_app() -> FastAPI:
    settings.validate_runtime_safety()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_headers=["*"],
        allow_methods=["*"],
        allow_origins=settings.cors_origins,
    )

    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
