import json
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_runtime.schemas import AgentArtifactRef, AgentRunEvent, AgentRunStep
from app.models import AgentRun, AgentRunEvent as DBAgentRunEvent, Artifact, Conversation
from app.services.artifact_discovery import create_artifacts_from_paths
from app.api.routes.sessions import persist_discovered_artifacts


def parse_sse_events(payload: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in payload.strip().split("\n\n"):
        event_name = "message"
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ").strip()
            if line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        if data is not None:
            events.append((event_name, data))
    return events


class FakeStreamingAdapter:
    def __init__(self, artifact_path: str):
        self.artifact_path = artifact_path
        self.seen_run_id: str | None = None

    async def stream_response_events(self, input_data):
        self.seen_run_id = input_data.run_id
        yield AgentRunEvent(
            run_id=input_data.run_id,
            event_type="stage_update",
            status="running",
            progress=35,
            payload={"protocol": "hermes.stream.v1", "hermesEventType": "stage_update"},
            step=AgentRunStep(
                id=f"{input_data.run_id}_stage_1",
                label="阶段 1：准备资料",
                status="completed",
                timestamp="2026-07-17T00:00:00Z",
            ),
        )
        yield AgentRunEvent(
            run_id=input_data.run_id,
            event_type="completion_signal",
            status="running",
            progress=80,
            payload={
                "protocol": "hermes.stream.v1",
                "hermesEventType": "completion_signal",
                "completionDetected": True,
            },
            step=AgentRunStep(
                id=f"{input_data.run_id}_stage_2",
                label="报告已生成。验证文件：",
                status="completed",
                timestamp="2026-07-17T00:00:01Z",
            ),
        )

    def get_last_artifact_paths(self) -> list[str]:
        return [self.artifact_path]

    def get_last_artifacts(self) -> list[AgentArtifactRef]:
        return [
            AgentArtifactRef(
                path=self.artifact_path,
                artifact_type="markdown_report",
                run_id=self.seen_run_id,
                source_dir=str(Path(self.artifact_path).parent),
            )
        ]

    def get_last_diagnostics(self) -> dict[str, object]:
        return {"adapter": "fake"}


@pytest.mark.asyncio
async def test_session_permissions_and_share_access(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
):
    create_response = await api_client.post(
        "/api/sessions",
        json={"title": "私有会话"},
        headers=auth_headers["owner"],
    )
    assert create_response.status_code == 200
    session_id = create_response.json()["id"]

    stranger_response = await api_client.get(
        f"/api/sessions/{session_id}/messages",
        headers=auth_headers["stranger"],
    )
    assert stranger_response.status_code == 404

    share_response = await api_client.patch(
        f"/api/sessions/{session_id}",
        json={"shareWithEmail": "shared@example.com"},
        headers=auth_headers["owner"],
    )
    assert share_response.status_code == 200
    assert share_response.json()["visibility"] == "shared"
    assert share_response.json()["sharedWith"][0]["email"] == "shared@example.com"

    shared_response = await api_client.get(
        f"/api/sessions/{session_id}/messages",
        headers=auth_headers["shared"],
    )
    assert shared_response.status_code == 200

    non_owner_delete = await api_client.delete(
        f"/api/sessions/{session_id}",
        headers=auth_headers["shared"],
    )
    assert non_owner_delete.status_code == 403


@pytest.mark.asyncio
async def test_username_login_and_admin_user_list_password_mask(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
):
    login_response = await api_client.post(
        "/api/auth/login",
        json={"identifier": "owner", "password": "ownerpass"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["username"] == "owner"

    users_response = await api_client.get(
        "/api/admin/users",
        headers=auth_headers["admin"],
    )
    assert users_response.status_code == 200
    users = users_response.json()
    assert any(user["username"] == "admin" for user in users)
    assert all("passwordMask" in user for user in users)
    assert all(user["passwordMask"] in {"********", "未设置"} for user in users)
    assert all("conversationCount" in user for user in users)
    assert all("createdAt" in user for user in users)
    assert all("updatedAt" in user for user in users)

    owner = next(user for user in users if user["username"] == "owner")
    reset_response = await api_client.post(
        f"/api/admin/users/{owner['id']}/password",
        json={"newPassword": "nextpass"},
        headers=auth_headers["admin"],
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["passwordMask"] == "********"

    relogin_response = await api_client.post(
        "/api/auth/login",
        json={"identifier": "owner", "password": "nextpass"},
    )
    assert relogin_response.status_code == 200


@pytest.mark.asyncio
async def test_artifact_discovery_persists_and_respects_permissions(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
    db_sessionmaker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
):
    session_response = await api_client.post(
        "/api/sessions",
        json={"title": "Artifact 会话"},
        headers=auth_headers["owner"],
    )
    session_id = session_response.json()["id"]
    report_path = tmp_path / "report.md"
    report_path.write_text("# 集成测试报告\n\n正文", encoding="utf-8")
    discovered = create_artifacts_from_paths(session_id, [str(report_path)], "run_test")

    async with db_sessionmaker() as db:
        stored = await persist_discovered_artifacts(db, session_id, discovered, "run_test")
        artifact_id = stored[0].id

    owner_artifact = await api_client.get(
        f"/api/artifacts/{artifact_id}",
        headers=auth_headers["owner"],
    )
    assert owner_artifact.status_code == 200
    assert owner_artifact.json()["type"] == "markdown_report"
    assert owner_artifact.json()["content"].startswith("# 集成测试报告")

    stranger_artifact = await api_client.get(
        f"/api/artifacts/{artifact_id}",
        headers=auth_headers["stranger"],
    )
    assert stranger_artifact.status_code == 404


@pytest.mark.asyncio
async def test_agent_run_sse_persists_events_and_artifact(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
    db_sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    report_path = tmp_path / "final_report.md"
    report_path.write_text("# SSE 报告\n\n已生成。", encoding="utf-8")
    fake_adapter = FakeStreamingAdapter(str(report_path))

    def fake_resolve_adapter(model_id=None, adapter_key=None):
        return "hermes", fake_adapter

    monkeypatch.setattr(
        "app.api.routes.agent_runs._resolve_adapter",
        fake_resolve_adapter,
    )

    session_response = await api_client.post(
        "/api/sessions",
        json={"title": "SSE 会话"},
        headers=auth_headers["owner"],
    )
    session_id = session_response.json()["id"]

    response = await api_client.post(
        f"/api/sessions/{session_id}/messages/stream",
        json={"content": "请生成报告", "skillKey": "deep_research", "modelId": "model_hermes"},
        headers=auth_headers["owner"],
    )
    assert response.status_code == 200
    events = parse_sse_events(response.text)
    event_names = [name for name, _ in events]
    assert "run_started" in event_names
    assert event_names.count("assistant_delta") == 2
    assert "artifact_created" in event_names
    assert "assistant_done" in event_names

    run_id = next(data["runId"] for name, data in events if name == "run_started")
    artifact_event = next(data for name, data in events if name == "artifact_created")
    assert artifact_event["artifact"]["type"] == "markdown_report"
    assert artifact_event["runId"] == run_id

    async with db_sessionmaker() as db:
        run = await db.get(AgentRun, run_id)
        assert run is not None
        assert run.status == "completed"
        run_events = (
            await db.execute(
                select(DBAgentRunEvent).where(DBAgentRunEvent.run_id == run_id)
            )
        ).scalars().all()
        assert {event.event_type for event in run_events} >= {
            "started",
            "stage_update",
            "completion_signal",
            "artifact_created",
            "completed",
        }
        artifacts = (
            await db.execute(select(Artifact).where(Artifact.run_id == run_id))
        ).scalars().all()
        assert len(artifacts) == 1
        assert artifacts[0].content == "# SSE 报告\n\n已生成。"


@pytest.mark.asyncio
async def test_public_session_read_access_but_not_owner_actions(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
    db_sessionmaker: async_sessionmaker[AsyncSession],
):
    create_response = await api_client.post(
        "/api/sessions",
        json={"title": "公开会话", "visibility": "public"},
        headers=auth_headers["owner"],
    )
    session_id = create_response.json()["id"]

    list_response = await api_client.get("/api/sessions", headers=auth_headers["stranger"])
    assert list_response.status_code == 200
    assert any(session["id"] == session_id for session in list_response.json())

    async with db_sessionmaker() as db:
        conversation = await db.get(Conversation, session_id)
        assert conversation is not None
        assert conversation.visibility == "public"

    write_response = await api_client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "尝试写入"},
        headers=auth_headers["stranger"],
    )
    assert write_response.status_code == 403
