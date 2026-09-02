# File purpose: Persists run-scoped artifact watcher states before final artifact discovery.
# Main declarations: sync_run_artifact_state upserts pending, staging, ready, or failed rows.

from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun, Artifact, RunArtifact

VALID_ARTIFACT_STATES = {"pending", "staging", "ready", "failed"}
VALID_ARTIFACT_TYPES = {
    "markdown_report",
    "html_page",
    "ppt_deck",
    "image_result",
    "data_table",
    "chart",
    "debug_json",
}
VALID_ARTIFACT_ROLES = {"primary", "intermediate", "preview_fallback"}


async def sync_run_artifact_state(
    db: AsyncSession,
    run: AgentRun,
    payload: dict[str, object],
) -> Artifact | None:
    path = str(payload.get("artifactPath") or "").strip()
    state = str(payload.get("artifactState") or "").strip()
    artifact_type = str(payload.get("artifactType") or "").strip()
    entry_id = str(payload.get("manifestEntryId") or "").strip()
    if not path or state not in VALID_ARTIFACT_STATES:
        return None
    if artifact_type not in VALID_ARTIFACT_TYPES:
        return None

    identity_filters = [Artifact.artifact_metadata["watcherPath"].as_string() == path]
    if entry_id:
        identity_filters.append(
            Artifact.artifact_metadata["manifestEntryId"].as_string() == entry_id
        )
    result = await db.execute(
        select(Artifact)
        .outerjoin(RunArtifact, RunArtifact.artifact_id == Artifact.id)
        .where(
            Artifact.conversation_id == run.conversation_id,
            Artifact.type == artifact_type,
            or_(Artifact.run_id == run.id, RunArtifact.run_id == run.id),
            or_(*identity_filters),
        )
        .order_by(Artifact.created_at.desc())
        .limit(1)
    )
    artifact = result.scalars().unique().one_or_none()
    metadata = dict(artifact.artifact_metadata or {}) if artifact else {}
    artifact_role = str(
        payload.get("artifactRole") or metadata.get("artifactRole") or "primary"
    ).strip()
    if artifact_role not in VALID_ARTIFACT_ROLES:
        artifact_role = "primary"
    incoming_mtime = payload.get("mtimeNs")
    previous_mtime = metadata.get("mtimeNs")
    if (
        artifact is not None
        and artifact.status in {"ready", "failed"}
        and state in {"pending", "staging"}
        and isinstance(previous_mtime, int)
        and (not isinstance(incoming_mtime, int) or incoming_mtime <= previous_mtime)
    ):
        return artifact
    metadata.update(
        {
            "adapterProtocol": payload.get("manifestSchema"),
            "artifactRole": artifact_role,
            "manifestEntryId": entry_id or metadata.get("manifestEntryId"),
            "watcherPath": path,
            "path": path,
            "originalPath": path,
            "sizeBytes": payload.get("sizeBytes"),
            "mtimeNs": payload.get("mtimeNs"),
            "stableAt": payload.get("stableAt"),
            "watcherError": payload.get("error"),
            "manifestPathScope": payload.get("pathScope"),
        }
    )

    if artifact is None:
        artifact = Artifact(
            conversation_id=run.conversation_id,
            run_id=run.id,
            type=artifact_type,
            title=str(payload.get("artifactTitle") or Path(path).stem),
            status=state,
            artifact_metadata=metadata,
            is_primary=artifact_type != "debug_json" and artifact_role == "primary",
        )
        db.add(artifact)
        await db.flush()
        db.add(RunArtifact(run_id=run.id, artifact_id=artifact.id))
    else:
        artifact.type = artifact_type
        artifact.title = str(payload.get("artifactTitle") or artifact.title)
        artifact.status = state
        artifact.artifact_metadata = metadata
        artifact.is_primary = artifact_type != "debug_json" and artifact_role == "primary"
    return artifact


__all__ = ["sync_run_artifact_state"]
