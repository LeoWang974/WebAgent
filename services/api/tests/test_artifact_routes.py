# File purpose: Verifies artifact list visibility and durable per-Run filtering contracts.
# Main declarations: route tests cover ready-state filtering, developer diagnostics, admin access,
# and RunArtifact ownership overrides.

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import AgentRun, Artifact, Conversation, RunArtifact


@pytest.mark.asyncio
async def test_run_artifact_list_is_authoritative_and_hides_unready_rows(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
    db_sessionmaker: async_sessionmaker[AsyncSession],
    seeded_users,
):
    conversation_id = "artifact-route-conversation"
    original_run_id = "artifact-route-original-run"
    current_run_id = "artifact-route-current-run"
    ready_artifact_id = "artifact-route-ready"
    failed_artifact_id = "artifact-route-failed"

    async with db_sessionmaker() as db:
        db.add(
            Conversation(
                id=conversation_id,
                user_id=seeded_users["owner"].id,
                title="Artifact route checks",
            )
        )
        db.add_all(
            [
                AgentRun(
                    id=original_run_id,
                    conversation_id=conversation_id,
                    status="completed",
                    title="Original run",
                ),
                AgentRun(
                    id=current_run_id,
                    conversation_id=conversation_id,
                    status="completed",
                    title="Current run",
                ),
            ]
        )
        db.add_all(
            [
                Artifact(
                    id=ready_artifact_id,
                    conversation_id=conversation_id,
                    run_id=original_run_id,
                    type="markdown_report",
                    title="Ready report",
                    status="ready",
                    artifact_metadata={"artifactRole": "primary"},
                ),
                Artifact(
                    id=failed_artifact_id,
                    conversation_id=conversation_id,
                    run_id=current_run_id,
                    type="ppt_deck",
                    title="Incomplete deck",
                    status="failed",
                    artifact_metadata={"artifactRole": "primary"},
                ),
            ]
        )
        await db.flush()
        db.add(RunArtifact(run_id=current_run_id, artifact_id=ready_artifact_id))
        await db.commit()

    response = await api_client.get(
        "/api/artifacts",
        params={"sessionId": conversation_id, "runId": current_run_id},
        headers=auth_headers["owner"],
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [ready_artifact_id]
    assert response.json()[0]["runId"] == current_run_id

    session_response = await api_client.get(
        f"/api/sessions/{conversation_id}/artifacts",
        headers=auth_headers["owner"],
    )
    assert session_response.status_code == 200
    assert [item["id"] for item in session_response.json()] == [ready_artifact_id]

    failed_detail = await api_client.get(
        f"/api/artifacts/{failed_artifact_id}",
        headers=auth_headers["owner"],
    )
    assert failed_detail.status_code == 404

    enable_developer_mode = await api_client.put(
        "/api/settings/interface",
        json={"developerMode": True},
        headers=auth_headers["owner"],
    )
    assert enable_developer_mode.status_code == 200

    developer_response = await api_client.get(
        "/api/artifacts",
        params={"sessionId": conversation_id, "runId": current_run_id},
        headers=auth_headers["owner"],
    )
    assert developer_response.status_code == 200
    assert {item["id"] for item in developer_response.json()} == {
        ready_artifact_id,
        failed_artifact_id,
    }


@pytest.mark.asyncio
async def test_admin_can_list_ready_artifacts_from_private_conversation(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
    db_sessionmaker: async_sessionmaker[AsyncSession],
    seeded_users,
):
    conversation_id = "artifact-route-private"
    artifact_id = "artifact-route-private-report"
    async with db_sessionmaker() as db:
        db.add(
            Conversation(
                id=conversation_id,
                user_id=seeded_users["owner"].id,
                title="Private artifact",
                visibility="private",
            )
        )
        db.add(
            Artifact(
                id=artifact_id,
                conversation_id=conversation_id,
                type="markdown_report",
                title="Private report",
                status="ready",
            )
        )
        await db.commit()

    response = await api_client.get(
        "/api/artifacts",
        params={"sessionId": conversation_id},
        headers=auth_headers["admin"],
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [artifact_id]
