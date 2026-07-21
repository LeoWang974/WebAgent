import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.services.skills_updater import (
    SkillsUpdateResult,
    default_openclaw_skills_dir,
    update_sensenova_skills,
)

logger = logging.getLogger(__name__)


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown skills update timezone %s, falling back to UTC", name)
        return ZoneInfo("UTC")


def next_weekly_run_at(
    now: datetime,
    *,
    weekday: int,
    hour: int,
    minute: int,
    timezone_name: str,
) -> datetime:
    tz = _timezone(timezone_name)
    local_now = now.astimezone(tz)
    target = datetime.combine(
        local_now.date(),
        time(hour=hour, minute=minute),
        tzinfo=tz,
    )
    days_until = (weekday - local_now.weekday()) % 7
    target += timedelta(days=days_until)
    if target <= local_now:
        target += timedelta(days=7)
    return target


async def run_configured_skills_update() -> SkillsUpdateResult:
    hermes_skills_dir = settings.hermes_skills_dir or f"{settings.hermes_home.rstrip('/')}/skills"
    openclaw_skills_dir = settings.openclaw_skills_dir or str(default_openclaw_skills_dir())
    return await update_sensenova_skills(
        repo_url=settings.skills_update_repo_url,
        cache_dir=settings.skills_update_cache_dir,
        source_subdir=settings.skills_update_source_subdir,
        branch=settings.skills_update_branch,
        hermes_skills_dir=hermes_skills_dir,
        openclaw_skills_dir=openclaw_skills_dir,
        wsl_distribution=settings.hermes_wsl_distribution,
    )


async def run_periodic_skills_update() -> None:
    if settings.skills_update_run_on_startup:
        try:
            await run_configured_skills_update()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Startup SenseNova skills update failed")

    while True:
        next_run = next_weekly_run_at(
            datetime.now(UTC),
            weekday=settings.skills_update_weekday,
            hour=settings.skills_update_hour,
            minute=settings.skills_update_minute,
            timezone_name=settings.skills_update_timezone,
        )
        delay_seconds = max(0.0, (next_run - datetime.now(next_run.tzinfo)).total_seconds())
        logger.info("Next SenseNova skills update scheduled at %s", next_run.isoformat())
        await asyncio.sleep(delay_seconds)
        try:
            await run_configured_skills_update()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled SenseNova skills update failed")


async def stop_skills_update_task(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
