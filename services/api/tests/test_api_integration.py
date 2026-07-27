import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from agent_runtime.schemas import AgentArtifactRef, AgentRunEvent, AgentRunStep
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.routes.sessions import persist_discovered_artifacts
from app.core.config import settings
from app.core.security import create_access_token
from app.models import AgentRun, Artifact, Conversation, Message, User
from app.models import AgentRunEvent as DBAgentRunEvent
from app.services.artifact_discovery import create_artifacts_from_paths


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
            event_type="stage_started",
            status="running",
            progress=35,
            payload={
                "protocol": "hermes.stream.v1",
                "hermesEventType": "stage_started",
                "rawHermesEventType": "stage_update",
            },
            step=AgentRunStep(
                id=f"{input_data.run_id}_stage_1",
                label="阶段 1：准备资料",
                status="completed",
                timestamp="2026-07-17T00:00:00Z",
            ),
        )
        yield AgentRunEvent(
            run_id=input_data.run_id,
            event_type="completed",
            status="running",
            progress=80,
            payload={
                "protocol": "hermes.stream.v1",
                "hermesEventType": "completed",
                "rawHermesEventType": "completion_signal",
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


class FakeHangingAdapter:
    async def stream_response_events(self, input_data):
        await asyncio.sleep(5)
        if False:
            yield None

    async def cancel_run(self, run_id: str) -> bool:
        return True

    def get_last_artifact_paths(self) -> list[str]:
        return []

    def get_last_artifacts(self) -> list[AgentArtifactRef]:
        return []

    def get_last_diagnostics(self) -> dict[str, object]:
        return {"adapter": "hanging", "stderr_tail": "no output before timeout"}


class FakeRawActivityAdapter:
    async def stream_response_events(self, input_data):
        yield AgentRunEvent(
            run_id=input_data.run_id,
            event_type="stage_started",
            status="running",
            progress=20,
            payload={"rawActivityHeartbeat": True},
            step=AgentRunStep(
                id=f"{input_data.run_id}_raw_activity",
                label="Hermes is still running; raw output is being received.",
                status="running",
                timestamp="2026-07-17T00:00:00Z",
            ),
        )

    def get_last_artifact_paths(self) -> list[str]:
        return []

    def get_last_artifacts(self) -> list[AgentArtifactRef]:
        return []

    def get_last_diagnostics(self) -> dict[str, object]:
        return {"adapter": "raw_activity"}


class FakeShortChatAdapter:
    def __init__(self):
        self.cancelled = False

    async def stream_response_events(self, input_data):
        yield AgentRunEvent(
            run_id=input_data.run_id,
            event_type="stage_started",
            status="running",
            progress=25,
            payload={"protocol": "hermes.stream.v1", "hermesEventType": "stage_started"},
            step=AgentRunStep(
                id=f"{input_data.run_id}_stage_1",
                label="你好，有什么可以帮你的？",
                status="completed",
                timestamp="2026-07-17T00:00:00Z",
            ),
        )
        await asyncio.sleep(5)

    async def cancel_run(self, run_id: str) -> bool:
        self.cancelled = True
        return True

    def get_last_artifact_paths(self) -> list[str]:
        return []

    def get_last_artifacts(self) -> list[AgentArtifactRef]:
        return []

    def get_last_diagnostics(self) -> dict[str, object]:
        return {"adapter": "short_chat"}


@pytest.mark.asyncio
async def test_register_accepts_username_without_email(api_client: AsyncClient):
    response = await api_client.post(
        "/api/auth/register",
        json={
            "nickname": "No Email User",
            "password": "test",
            "username": "no-email-user",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accessToken"]
    assert payload["user"]["email"] == "no-email-user@webagent.local"
    assert payload["user"]["username"] == "no-email-user"


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
async def test_admin_can_view_all_private_sessions(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
):
    create_response = await api_client.post(
        "/api/sessions",
        json={"title": "Owner private session"},
        headers=auth_headers["owner"],
    )
    assert create_response.status_code == 200
    session_id = create_response.json()["id"]

    stranger_list_response = await api_client.get(
        "/api/sessions",
        headers=auth_headers["stranger"],
    )
    assert stranger_list_response.status_code == 200
    assert all(session["id"] != session_id for session in stranger_list_response.json())

    admin_list_response = await api_client.get(
        "/api/sessions",
        headers=auth_headers["admin"],
    )
    assert admin_list_response.status_code == 200
    assert any(session["id"] == session_id for session in admin_list_response.json())

    admin_messages_response = await api_client.get(
        f"/api/sessions/{session_id}/messages",
        headers=auth_headers["admin"],
    )
    assert admin_messages_response.status_code == 200

    admin_delete_response = await api_client.delete(
        f"/api/sessions/{session_id}",
        headers=auth_headers["admin"],
    )
    assert admin_delete_response.status_code == 403


@pytest.mark.asyncio
async def test_debug_json_artifacts_require_developer_mode(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
    db_sessionmaker: async_sessionmaker[AsyncSession],
):
    create_response = await api_client.post(
        "/api/sessions",
        json={"title": "Debug artifacts"},
        headers=auth_headers["owner"],
    )
    assert create_response.status_code == 200
    session_id = create_response.json()["id"]

    async with db_sessionmaker() as db:
        db.add(
            Artifact(
                conversation_id=session_id,
                type="debug_json",
                title="briefing.json",
                status="ready",
                content='{"topic":"future food"}',
                artifact_metadata={"filename": "briefing.json"},
            )
        )
        await db.commit()

    hidden_response = await api_client.get(
        f"/api/sessions/{session_id}/artifacts",
        headers=auth_headers["owner"],
    )
    assert hidden_response.status_code == 200
    assert hidden_response.json() == []

    settings_response = await api_client.put(
        "/api/settings/interface",
        json={"developerMode": True},
        headers=auth_headers["owner"],
    )
    assert settings_response.status_code == 200
    assert settings_response.json()["developerMode"] is True

    visible_response = await api_client.get(
        f"/api/sessions/{session_id}/artifacts",
        headers=auth_headers["owner"],
    )
    assert visible_response.status_code == 200
    artifacts = visible_response.json()
    assert len(artifacts) == 1
    assert artifacts[0]["type"] == "debug_json"
    assert artifacts[0]["content"] == '{"topic":"future food"}'


@pytest.mark.asyncio
async def test_conversation_folder_create_assign_clear_and_public_listing(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
):
    folder_response = await api_client.post(
        "/api/sessions/folders",
        json={"name": "项目资料"},
        headers=auth_headers["owner"],
    )
    assert folder_response.status_code == 200
    folder = folder_response.json()

    duplicate_response = await api_client.post(
        "/api/sessions/folders",
        json={"name": "项目资料"},
        headers=auth_headers["owner"],
    )
    assert duplicate_response.status_code == 409

    create_response = await api_client.post(
        "/api/sessions",
        json={"folderId": folder["id"], "title": "目录中的会话"},
        headers=auth_headers["owner"],
    )
    assert create_response.status_code == 200
    session = create_response.json()
    assert session["folderId"] == folder["id"]

    list_folders_response = await api_client.get(
        "/api/sessions/folders",
        headers=auth_headers["owner"],
    )
    assert list_folders_response.status_code == 200
    assert [item["id"] for item in list_folders_response.json()] == [folder["id"]]

    clear_response = await api_client.patch(
        f"/api/sessions/{session['id']}",
        json={"folderId": None},
        headers=auth_headers["owner"],
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["folderId"] is None

    public_response = await api_client.post(
        "/api/sessions",
        json={"title": "公开资料", "visibility": "public"},
        headers=auth_headers["owner"],
    )
    assert public_response.status_code == 200
    public_id = public_response.json()["id"]

    stranger_list_response = await api_client.get(
        "/api/sessions",
        headers=auth_headers["stranger"],
    )
    assert stranger_list_response.status_code == 200
    assert any(session["id"] == public_id for session in stranger_list_response.json())

    delete_response = await api_client.delete(
        f"/api/sessions/folders/{folder['id']}",
        headers=auth_headers["owner"],
    )
    assert delete_response.status_code == 204


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
async def test_password_update_can_refresh_jwt(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
):
    update_response = await api_client.put(
        "/api/settings/profile/password",
        json={
            "currentPassword": "ownerpass",
            "newPassword": "nextpass",
            "relogin": True,
        },
        headers=auth_headers["owner"],
    )
    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["accessToken"]
    assert payload["user"]["username"] == "owner"

    me_response = await api_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {payload['accessToken']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "owner"

    old_password_response = await api_client.post(
        "/api/auth/login",
        json={"identifier": "owner", "password": "ownerpass"},
    )
    assert old_password_response.status_code == 401

    new_password_response = await api_client.post(
        "/api/auth/login",
        json={"identifier": "owner", "password": "nextpass"},
    )
    assert new_password_response.status_code == 200


@pytest.mark.asyncio
async def test_dev_auth_fallback_disabled_requires_real_jwt(
    api_client: AsyncClient,
    seeded_users: dict[str, User],
):
    previous = settings.allow_dev_auth_fallback
    settings.allow_dev_auth_fallback = False
    try:
        no_token_response = await api_client.get("/api/auth/me")
        assert no_token_response.status_code == 401

        dev_token_response = await api_client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer dev_token_owner@example.com"},
        )
        assert dev_token_response.status_code == 401

        real_token = create_access_token(seeded_users["owner"].id)
        real_token_response = await api_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {real_token}"},
        )
        assert real_token_response.status_code == 200
        assert real_token_response.json()["username"] == "owner"
    finally:
        settings.allow_dev_auth_fallback = previous


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
            (await db.execute(select(DBAgentRunEvent).where(DBAgentRunEvent.run_id == run_id)))
            .scalars()
            .all()
        )
        assert {event.event_type for event in run_events} >= {
            "started",
            "stage_started",
            "completed",
            "artifact_created",
        }
        artifacts = (
            (await db.execute(select(Artifact).where(Artifact.run_id == run_id))).scalars().all()
        )
        assert len(artifacts) == 1
        assert artifacts[0].content == "# SSE 报告\n\n已生成。"


@pytest.mark.asyncio
async def test_raw_activity_heartbeat_does_not_create_assistant_message(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
    db_sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
):
    fake_adapter = FakeRawActivityAdapter()

    def fake_resolve_adapter(model_id=None, adapter_key=None):
        return "hermes", fake_adapter

    monkeypatch.setattr(
        "app.api.routes.agent_runs._resolve_adapter",
        fake_resolve_adapter,
    )

    async def fake_discover_artifacts_with_retry(*args, **kwargs):
        return []

    monkeypatch.setattr(
        "app.api.routes.sessions.discover_artifacts_with_retry",
        fake_discover_artifacts_with_retry,
    )

    session_response = await api_client.post(
        "/api/sessions",
        json={"title": "Raw activity session"},
        headers=auth_headers["owner"],
    )
    session_id = session_response.json()["id"]

    response = await api_client.post(
        f"/api/sessions/{session_id}/messages/stream",
        json={
            "content": "run quietly",
            "skillKey": "deep_research",
            "modelId": "model_hermes",
        },
        headers=auth_headers["owner"],
    )
    assert response.status_code == 200
    events = parse_sse_events(response.text)
    event_names = [name for name, _ in events]
    assert "assistant_delta" not in event_names
    done_event = next(data for name, data in events if name == "assistant_done")

    async with db_sessionmaker() as db:
        messages = (
            (await db.execute(select(Message).where(Message.conversation_id == session_id)))
            .scalars()
            .all()
        )
        assert not any(
            message.content == "Hermes is still running; raw output is being received."
            for message in messages
        )
        run_events = (
            (
                await db.execute(
                    select(DBAgentRunEvent).where(DBAgentRunEvent.run_id == done_event["runId"])
                )
            )
            .scalars()
            .all()
        )
        assert any(event.event_type == "raw_activity" for event in run_events)


@pytest.mark.asyncio
async def test_cancel_agent_run_marks_cancelled(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
    db_sessionmaker: async_sessionmaker[AsyncSession],
):
    session_response = await api_client.post(
        "/api/sessions",
        json={"title": "Cancel run session"},
        headers=auth_headers["owner"],
    )
    session_id = session_response.json()["id"]

    run_response = await api_client.post(
        "/api/agent-runs",
        json={"content": "long task", "sessionId": session_id, "modelId": "model_hermes"},
        headers=auth_headers["owner"],
    )
    assert run_response.status_code == 200
    run_id = run_response.json()["id"]

    cancel_response = await api_client.post(
        f"/api/agent-runs/{run_id}/cancel",
        headers=auth_headers["owner"],
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    async with db_sessionmaker() as db:
        run = await db.get(AgentRun, run_id)
        assert run is not None
        assert run.status == "cancelled"
        events = (
            (await db.execute(select(DBAgentRunEvent).where(DBAgentRunEvent.run_id == run_id)))
            .scalars()
            .all()
        )
        assert any(event.event_type == "cancelled" for event in events)


@pytest.mark.asyncio
async def test_stale_running_run_recovers_as_disconnected(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
    db_sessionmaker: async_sessionmaker[AsyncSession],
):
    session_response = await api_client.post(
        "/api/sessions",
        json={"title": "Disconnected run session"},
        headers=auth_headers["owner"],
    )
    session_id = session_response.json()["id"]

    run_response = await api_client.post(
        "/api/agent-runs",
        json={"content": "long task", "sessionId": session_id, "modelId": "model_hermes"},
        headers=auth_headers["owner"],
    )
    run_id = run_response.json()["id"]

    async with db_sessionmaker() as db:
        run = await db.get(AgentRun, run_id)
        assert run is not None
        run.status = "running"
        run.updated_at = datetime.now(UTC) - timedelta(hours=2)
        await db.commit()

    list_response = await api_client.get(
        f"/api/agent-runs?session_id={session_id}",
        headers=auth_headers["owner"],
    )
    assert list_response.status_code == 200
    listed_run = next(item for item in list_response.json() if item["id"] == run_id)
    assert listed_run["status"] == "disconnected"


@pytest.mark.asyncio
async def test_agent_run_stream_idle_timeout_records_diagnostics(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
    db_sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
):
    fake_adapter = FakeHangingAdapter()

    def fake_resolve_adapter(model_id=None, adapter_key=None):
        return "hermes", fake_adapter

    monkeypatch.setattr(
        "app.api.routes.agent_runs._resolve_adapter",
        fake_resolve_adapter,
    )
    previous_idle_timeout = settings.agent_run_idle_timeout_seconds
    previous_overall_timeout = settings.agent_run_overall_timeout_seconds
    settings.agent_run_idle_timeout_seconds = 1
    settings.agent_run_overall_timeout_seconds = 10
    try:
        session_response = await api_client.post(
            "/api/sessions",
            json={"title": "Timeout run session"},
            headers=auth_headers["owner"],
        )
        session_id = session_response.json()["id"]

        response = await api_client.post(
            f"/api/sessions/{session_id}/messages/stream",
            json={
                "content": "wait forever",
                "skillKey": "deep_research",
                "modelId": "model_hermes",
            },
            headers=auth_headers["owner"],
        )
        assert response.status_code == 200
        events = parse_sse_events(response.text)
        done_event = next(data for name, data in events if name == "assistant_done")
        assert done_event["status"] == "failed"
        run_id = done_event["runId"]

        async with db_sessionmaker() as db:
            run = await db.get(AgentRun, run_id)
            assert run is not None
            assert run.status == "failed"
            run_events = (
                (await db.execute(select(DBAgentRunEvent).where(DBAgentRunEvent.run_id == run_id)))
                .scalars()
                .all()
            )
            diagnostic = next(event for event in run_events if event.event_type == "diagnostic")
            assert diagnostic.payload["hermesDiagnostics"]["adapter"] == "hanging"
            assert (
                diagnostic.payload["hermesDiagnostics"]["stderr_tail"] == "no output before timeout"
            )
    finally:
        settings.agent_run_idle_timeout_seconds = previous_idle_timeout
        settings.agent_run_overall_timeout_seconds = previous_overall_timeout


@pytest.mark.asyncio
async def test_short_chat_fast_closes_after_first_response(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
    db_sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
):
    fake_adapter = FakeShortChatAdapter()

    def fake_resolve_adapter(model_id=None, adapter_key=None):
        return "hermes", fake_adapter

    monkeypatch.setattr(
        "app.api.routes.agent_runs._resolve_adapter",
        fake_resolve_adapter,
    )

    session_response = await api_client.post(
        "/api/sessions",
        json={"title": "Short chat session"},
        headers=auth_headers["owner"],
    )
    session_id = session_response.json()["id"]

    started_at = datetime.now(UTC)
    response = await api_client.post(
        f"/api/sessions/{session_id}/messages/stream",
        json={"content": "你好", "modelId": "model_hermes"},
        headers=auth_headers["owner"],
    )
    elapsed = (datetime.now(UTC) - started_at).total_seconds()
    assert response.status_code == 200
    assert elapsed < 4

    events = parse_sse_events(response.text)
    event_names = [name for name, _ in events]
    assert event_names.count("assistant_delta") == 1
    assert "artifact_created" not in event_names
    done_event = next(data for name, data in events if name == "assistant_done")
    assert done_event["status"] == "completed"
    assert done_event["message"]["content"] == "你好，有什么可以帮你的？"
    assert fake_adapter.cancelled is True

    async with db_sessionmaker() as db:
        run = await db.get(AgentRun, done_event["runId"])
        assert run is not None
        assert run.status == "completed"
        run_events = (
            (await db.execute(select(DBAgentRunEvent).where(DBAgentRunEvent.run_id == run.id)))
            .scalars()
            .all()
        )
        assert not any(event.event_type == "diagnostic" for event in run_events)
        fast_close_event = next(
            event for event in run_events if (event.payload or {}).get("shortChatFastClose") is True
        )
        assert fast_close_event.payload["artifactDiscoverySkipped"] is True


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
