import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun, AgentRunEvent, Artifact, Conversation
from app.services.runtime_environment import runtime_root as user_runtime_root


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


def _expired_runtime_targets(
    root: Path,
    user_root: Path,
    cutoff: datetime,
) -> list[Path]:
    targets: list[Path] = []
    for directory in (root / "hermes-prompts", root / "hermes-runs"):
        if directory.is_dir():
            targets.extend(child for child in directory.iterdir() if _is_expired(child, cutoff))

    if user_root.is_dir():
        for runs_dir in user_root.glob("*/conversations/*/runs"):
            if runs_dir.is_dir():
                targets.extend(
                    child for child in runs_dir.iterdir() if _is_expired(child, cutoff)
                )
    return targets


def _expired_raw_logs(repo_root: Path, cutoff: datetime) -> list[Path]:
    logs_root = repo_root / "logs"
    if not logs_root.is_dir():
        return []
    return [
        path
        for path in logs_root.glob("hermes-raw-*.log")
        if path.is_file() and _is_expired(path, cutoff)
    ]


def cleanup_expired_runtime_files(
    *,
    max_age_days: int = 14,
    repo_root: Path | None = None,
) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    repository = repo_root or Path(__file__).resolve().parents[4]
    root = runtime_root(repository)
    configured_user_root = root / "users" if repo_root is not None else user_runtime_root()
    deleted = 0

    targets = _expired_runtime_targets(root, configured_user_root, cutoff)
    targets.extend(_expired_raw_logs(repository, cutoff))
    for target in targets:
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
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
