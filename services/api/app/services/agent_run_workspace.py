import json
import re
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Artifact


def safe_run_path_segment(value: str, fallback: str = "run") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value).strip(" .-")
    return cleaned[:96] or fallback


def run_workspace_dir(
    run_id: str,
    conversation_id: str | None = None,
    user_id: str | None = None,
) -> Path:
    root = Path(settings.agent_run_workspace_root)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[4] / root
    user_part = safe_run_path_segment(user_id or "anonymous", "user")
    conversation_part = safe_run_path_segment(conversation_id or "conversation")
    run_part = safe_run_path_segment(run_id)
    path = root / user_part / conversation_part / run_part
    path.mkdir(parents=True, exist_ok=True)
    package_marker = path / "package.json"
    if not package_marker.exists():
        package_marker.write_text(
            json.dumps(
                {
                    "name": f"webagent-run-{run_part.lower()}",
                    "private": True,
                    "version": "0.0.0",
                },
                ensure_ascii=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return path


def run_artifacts_dir(
    run_id: str,
    conversation_id: str | None = None,
    user_id: str | None = None,
) -> Path:
    path = run_workspace_dir(run_id, conversation_id, user_id) / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def stage_conversation_artifacts(
    db: AsyncSession,
    conversation_id: str,
    workspace: Path,
    *,
    limit: int = 8,
    mirror_dirs: tuple[Path, ...] = (),
) -> list[Path]:
    """Expose recent primary artifacts in every directory Hermes may use as its cwd."""
    result = await db.execute(
        select(Artifact)
        .where(
            Artifact.conversation_id == conversation_id,
            Artifact.is_primary.is_(True),
            Artifact.status == "ready",
        )
        .order_by(Artifact.created_at.desc())
        .limit(limit)
    )
    context_dir = workspace / "context"
    destination_dirs = tuple(dict.fromkeys((context_dir, workspace, *mirror_dirs)))
    staged: list[Path] = []

    for artifact in result.scalars().all():
        metadata = artifact.artifact_metadata or {}
        source = next(
            (
                Path(value)
                for value in (metadata.get("path"), metadata.get("originalPath"))
                if isinstance(value, str) and value and Path(value).is_file()
            ),
            None,
        )
        if source is None:
            continue

        filename = safe_run_path_segment(source.name, f"artifact-{artifact.id[:8]}")
        primary_destination: Path | None = None
        for destination_dir in destination_dirs:
            destination_dir.mkdir(parents=True, exist_ok=True)
            destination = destination_dir / filename
            if destination.exists() and destination.resolve() == source.resolve():
                if destination_dir == context_dir:
                    primary_destination = destination
                continue
            if destination.exists():
                destination = destination_dir / f"{artifact.id[:8]}-{filename}"
            shutil.copy2(source, destination)
            if destination_dir == context_dir:
                primary_destination = destination
        if primary_destination is not None:
            staged.append(primary_destination)

    return staged
