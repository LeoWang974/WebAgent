import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun, AgentRunEvent, Artifact, Conversation


@dataclass(frozen=True)
class CleanupResult:
    disconnected_runs_deleted: int = 0
    orphan_artifacts_deleted: int = 0
    orphan_artifacts_unlinked: int = 0
    runtime_files_deleted: int = 0


def runtime_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[4]
    return root / "runtime"


def _is_expired(path: Path, cutoff: datetime) -> bool:
    try:
        timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return False
    return timestamp < cutoff


def cleanup_expired_runtime_files(
    *,
    max_age_days: int = 14,
    repo_root: Path | None = None,
) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    root = runtime_root(repo_root)
    targets = [
        root / "hermes-prompts",
        root / "hermes-runs",
    ]
    deleted = 0

    for target in targets:
        if not target.exists():
            continue
        for child in target.iterdir():
            if not _is_expired(child, cutoff):
                continue
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
                deleted += 1
            except OSError:
                continue

    return deleted


async def cleanup_orphan_artifacts(db: AsyncSession) -> tuple[int, int]:
    conversation_ids = select(Conversation.id)
    orphan_result = await db.execute(
        select(Artifact.id).where(Artifact.conversation_id.not_in(conversation_ids))
    )
    orphan_ids = list(orphan_result.scalars().all())
    deleted = 0
    if orphan_ids:
        result = await db.execute(delete(Artifact).where(Artifact.id.in_(orphan_ids)))
        deleted = result.rowcount or 0

    run_ids = select(AgentRun.id)
    unlink_result = await db.execute(
        update(Artifact)
        .where(Artifact.run_id.is_not(None), Artifact.run_id.not_in(run_ids))
        .values(run_id=None)
    )
    unlinked = unlink_result.rowcount or 0
    await db.commit()
    return deleted, unlinked


async def cleanup_long_disconnected_runs(
    db: AsyncSession,
    *,
    max_age_days: int = 30,
) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    run_result = await db.execute(
        select(AgentRun.id).where(
            AgentRun.status == "disconnected",
            AgentRun.updated_at < cutoff,
        )
    )
    run_ids = list(run_result.scalars().all())
    if not run_ids:
        return 0

    await db.execute(update(Artifact).where(Artifact.run_id.in_(run_ids)).values(run_id=None))
    await db.execute(delete(AgentRunEvent).where(AgentRunEvent.run_id.in_(run_ids)))
    result = await db.execute(delete(AgentRun).where(AgentRun.id.in_(run_ids)))
    await db.commit()
    return result.rowcount or 0


async def run_data_cleanup(
    db: AsyncSession,
    *,
    disconnected_run_max_age_days: int = 30,
    runtime_file_max_age_days: int = 14,
    repo_root: Path | None = None,
) -> CleanupResult:
    runtime_deleted = cleanup_expired_runtime_files(
        max_age_days=runtime_file_max_age_days,
        repo_root=repo_root,
    )
    orphan_deleted, orphan_unlinked = await cleanup_orphan_artifacts(db)
    disconnected_deleted = await cleanup_long_disconnected_runs(
        db,
        max_age_days=disconnected_run_max_age_days,
    )
    return CleanupResult(
        disconnected_runs_deleted=disconnected_deleted,
        orphan_artifacts_deleted=orphan_deleted,
        orphan_artifacts_unlinked=orphan_unlinked,
        runtime_files_deleted=runtime_deleted,
    )
