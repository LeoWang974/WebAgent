# File purpose: Implements the cleanup backend service workflow.
# Main declarations: CleanupResult defines cleanup result state or behavior; _repo_runtime_dir
# handles repo runtime dir; _is_expired handles is expired; _deletion_path handles deletion path;
# _remove_runtime_target handles remove runtime target; _expired_runtime_targets handles expired
# runtime targets; _expired_raw_logs handles expired raw logs; cleanup_expired_runtime_files
# handles cleanup expired runtime files; cleanup_orphan_artifacts handles cleanup orphan
# artifacts; cleanup_long_disconnected_runs handles cleanup long disconnected runs;
# run_data_cleanup runs data cleanup.

import asyncio
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun, AgentRunEvent, Artifact, Conversation
from app.services.runtime_environment import runtime_root as configured_user_runtime_dir


@dataclass(frozen=True)
class CleanupResult:
    disconnected_runs_deleted: int = 0
    orphan_artifacts_deleted: int = 0
    orphan_artifacts_unlinked: int = 0
    runtime_files_deleted: int = 0


def _repo_runtime_dir(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[4]
    return root / "runtime"


def _is_expired(path: Path, cutoff: datetime) -> bool:
    try:
        timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return False
    return timestamp < cutoff


def _deletion_path(path: Path) -> str:
    resolved = str(path.resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        trimmed = resolved.lstrip("\\")
        return f"\\\\?\\UNC\\{trimmed}"
    return f"\\\\?\\{resolved}"


def _remove_runtime_target(target: Path) -> None:
    deletion_path = _deletion_path(target)
    if target.is_dir():
        shutil.rmtree(deletion_path)
    else:
        Path(deletion_path).unlink()


def _expired_runtime_targets(
    root: Path,
    user_root: Path,
    cutoff: datetime,
) -> list[Path]:
    targets: set[Path] = set()
    agent_runs_root = root / "agent-runs"
    if agent_runs_root.is_dir():
        run_directories = {
            marker.parent
            for marker in agent_runs_root.rglob("package.json")
            if marker.is_file()
        }
        targets.update(path for path in run_directories if _is_expired(path, cutoff))
        for child in agent_runs_root.iterdir():
            if child.is_file() and _is_expired(child, cutoff):
                targets.add(child)
            elif child.is_dir() and not any(
                run_dir == child or child in run_dir.parents for run_dir in run_directories
            ):
                # Legacy versions stored one Run directly below agent-runs.
                if _is_expired(child, cutoff):
                    targets.add(child)

    for directory in (root / "hermes-prompts", root / "hermes-runs"):
        if directory.is_dir():
            targets.update(child for child in directory.iterdir() if _is_expired(child, cutoff))

    if user_root.is_dir():
        for runs_dir in user_root.glob("*/conversations/*/runs"):
            if runs_dir.is_dir():
                targets.update(
                    child for child in runs_dir.iterdir() if _is_expired(child, cutoff)
                )
    return sorted(targets, key=str)


def _expired_raw_logs(repo_root: Path, cutoff: datetime) -> list[Path]:
    logs_root = repo_root / "logs"
    if not logs_root.is_dir():
        return []
    return [
        path
        for path in logs_root.glob("*.log")
        if path.is_file() and _is_expired(path, cutoff)
    ]


def cleanup_expired_runtime_files(
    *,
    max_age_days: int = 14,
    repo_root: Path | None = None,
) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    repository = repo_root or Path(__file__).resolve().parents[4]
    root = _repo_runtime_dir(repository)
    configured_user_root = (
        root / "users" if repo_root is not None else configured_user_runtime_dir()
    )
    deleted = 0

    targets = _expired_runtime_targets(root, configured_user_root, cutoff)
    targets.extend(_expired_raw_logs(repository, cutoff))
    for target in targets:
        try:
            _remove_runtime_target(target)
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
    runtime_deleted = await asyncio.to_thread(
        cleanup_expired_runtime_files,
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
