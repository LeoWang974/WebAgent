# File purpose: Verifies watcher artifact states persist once per Agent Run.
# Main declarations: test_sync_run_artifact_state_updates_one_run_artifact checks state updates.

import pytest
from sqlalchemy import select

from app.models import AgentRun, Artifact, Conversation, RunArtifact
from app.services.artifact_state_service import sync_run_artifact_state


@pytest.mark.asyncio
async def test_sync_run_artifact_state_updates_one_run_artifact(
    db_sessionmaker,
    seeded_users,
):
    conversation_id = "conversation-watcher-state"
    run_id = "run-watcher-state"
    async with db_sessionmaker() as db:
        db.add(
            Conversation(
                id=conversation_id,
                user_id=seeded_users["owner"].id,
                title="Watcher state",
            )
        )
        run = AgentRun(
            id=run_id,
            conversation_id=conversation_id,
            status="running",
            title="Watcher state",
        )
        db.add(run)
        await db.commit()

        base_payload = {
            "artifactPath": "/runtime/report.md",
            "artifactType": "markdown_report",
            "artifactTitle": "report",
            "manifestEntryId": "entry-1",
            "manifestSchema": "webagent.artifacts.v3",
        }
        for status in ("pending", "staging", "ready"):
            await sync_run_artifact_state(
                db,
                run,
                {**base_payload, "artifactState": status},
            )
            await db.commit()

        artifacts = (
            await db.execute(select(Artifact).where(Artifact.run_id == run_id))
        ).scalars().all()
        links = (
            await db.execute(select(RunArtifact).where(RunArtifact.run_id == run_id))
        ).scalars().all()

    assert len(artifacts) == 1
    assert artifacts[0].status == "ready"
    assert artifacts[0].artifact_metadata["manifestEntryId"] == "entry-1"
    assert len(links) == 1


@pytest.mark.asyncio
async def test_sync_run_artifact_state_ignores_older_status_regression(
    db_sessionmaker,
    seeded_users,
):
    conversation_id = "conversation-watcher-regression"
    run_id = "run-watcher-regression"
    async with db_sessionmaker() as db:
        db.add(
            Conversation(
                id=conversation_id,
                user_id=seeded_users["owner"].id,
                title="Watcher regression",
            )
        )
        run = AgentRun(
            id=run_id,
            conversation_id=conversation_id,
            status="running",
            title="Watcher regression",
        )
        db.add(run)
        await db.commit()
        payload = {
            "artifactPath": "/runtime/report.md",
            "artifactType": "markdown_report",
            "artifactTitle": "report",
            "manifestEntryId": "entry-regression",
            "manifestSchema": "webagent.artifacts.v3",
        }
        artifact = await sync_run_artifact_state(
            db,
            run,
            {**payload, "artifactState": "ready", "mtimeNs": 20},
        )
        await db.commit()
        regressed = await sync_run_artifact_state(
            db,
            run,
            {**payload, "artifactState": "staging", "mtimeNs": 10},
        )

    assert artifact is not None
    assert regressed is not None
    assert regressed.status == "ready"
    assert regressed.artifact_metadata["mtimeNs"] == 20


@pytest.mark.asyncio
async def test_sync_run_artifact_state_preserves_intermediate_role(
    db_sessionmaker,
    seeded_users,
):
    conversation_id = "conversation-watcher-role"
    run_id = "run-watcher-role"
    async with db_sessionmaker() as db:
        db.add(
            Conversation(
                id=conversation_id,
                user_id=seeded_users["owner"].id,
                title="Watcher role",
            )
        )
        run = AgentRun(
            id=run_id,
            conversation_id=conversation_id,
            status="running",
            title="Watcher role",
        )
        db.add(run)
        await db.commit()

        payload = {
            "artifactPath": "/runtime/plan.json",
            "artifactType": "debug_json",
            "artifactTitle": "plan",
            "manifestEntryId": "entry-plan",
            "manifestSchema": "webagent.artifacts.v3",
            "artifactRole": "intermediate",
        }
        artifact = await sync_run_artifact_state(
            db,
            run,
            {**payload, "artifactState": "pending"},
        )
        await db.commit()

        assert artifact is not None
        assert artifact.is_primary is False
        assert artifact.artifact_metadata["artifactRole"] == "intermediate"
