# File purpose: Verifies durable per-Run artifact ownership and cross-Run path reuse.
# Main declarations: test_reused_path_creates_artifact_and_relationship_for_each_run verifies
# historical path and hash reuse never suppresses a new Run's artifact record.

import pytest
from sqlalchemy import select

from app import schemas
from app.models import AgentRun, Artifact, Conversation, RunArtifact
from app.services.session_artifacts import persist_discovered_artifacts


@pytest.mark.asyncio
async def test_reused_path_creates_artifact_and_relationship_for_each_run(
    db_sessionmaker,
    seeded_users,
):
    conversation_id = "conversation-artifact-ownership"
    run_ids = ("run-artifact-owner-1", "run-artifact-owner-2")
    shared_metadata = {
        "path": "/reports/reused-report.md",
        "originalPath": "/reports/reused-report.md",
        "contentHash": "same-content-hash",
    }

    async with db_sessionmaker() as db:
        db.add(
            Conversation(
                id=conversation_id,
                user_id=seeded_users["owner"].id,
                title="Artifact ownership",
            )
        )
        for run_id in run_ids:
            db.add(
                AgentRun(
                    id=run_id,
                    conversation_id=conversation_id,
                    status="completed",
                    title="Artifact test",
                )
            )
        await db.commit()

        for index, run_id in enumerate(run_ids, start=1):
            discovered = [
                schemas.Artifact(
                    id=f"discovered-{index}",
                    session_id=conversation_id,
                    run_id=run_id,
                    type="markdown_report",
                    title="reused-report",
                    status="ready",
                    metadata=dict(shared_metadata),
                )
            ]
            stored = await persist_discovered_artifacts(
                db,
                conversation_id,
                discovered,
                run_id,
            )
            assert len(stored) == 1
            assert stored[0].run_id == run_id

        artifacts = (
            await db.execute(
                select(Artifact)
                .where(Artifact.conversation_id == conversation_id)
                .order_by(Artifact.run_id)
            )
        ).scalars().all()
        relationships = (
            await db.execute(
                select(RunArtifact).where(RunArtifact.run_id.in_(run_ids))
            )
        ).scalars().all()
        second_run_artifacts = (
            await db.execute(
                select(Artifact).where(
                    Artifact.run_artifacts.any(RunArtifact.run_id == run_ids[1])
                )
            )
        ).scalars().all()

    assert [artifact.run_id for artifact in artifacts] == list(run_ids)
    assert len({artifact.id for artifact in artifacts}) == 2
    assert {(item.run_id, item.artifact_id) for item in relationships} == {
        (artifact.run_id, artifact.id) for artifact in artifacts
    }
    assert [artifact.id for artifact in second_run_artifacts] == [artifacts[1].id]
