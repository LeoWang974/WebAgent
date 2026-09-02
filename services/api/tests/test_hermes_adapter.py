# File purpose: Verifies test hermes adapter behavior and its regression contracts.
# Main declarations: test_hermes_adapter_has_no_skill_mapping_helpers verifies hermes adapter has
# no skill mapping helpers; test_hermes_chat_command_starts_in_run_workspace verifies hermes chat
# command starts in run workspace; test_hermes_stream_forwards_prompt_verbatim verifies hermes
# stream forwards prompt verbatim; test_final_discovery_scans_the_run_runtime_root verifies final
# discovery scans the run runtime root; test_final_discovery_ignores_runtime_dependencies verifies
# final discovery ignores runtime dependencies.

from datetime import datetime, timedelta

import pytest

from app.integrations.hermes import AgentRunCreate, HermesAdapter
from app.integrations.hermes.cli import HermesCliWrapper, HermesStreamEvent
from app.services.model_runtime_config import ModelRuntimeConfig


def test_hermes_adapter_has_no_skill_mapping_helpers():
    adapter = HermesAdapter()

    assert not hasattr(adapter, "_get_skills_for_skill")
    assert not hasattr(adapter, "_get_toolsets_for_skill")
    assert not hasattr(adapter, "_build_runtime_prompt")


@pytest.mark.asyncio
async def test_hermes_health_check_probes_configured_model(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        is_success = True

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse()

    monkeypatch.setattr(
        "app.integrations.hermes.adapter.httpx.AsyncClient",
        lambda **kwargs: (captured.update(client_kwargs=kwargs) or FakeClient()),
    )
    monkeypatch.setattr(
        "app.integrations.hermes.adapter.settings.sensenova_ca_bundle",
        "C:/certs/sensenova-ca.pem",
    )
    adapter = HermesAdapter(
        model_runtime_config=ModelRuntimeConfig(
            model_config_id="model-1",
            provider="sensenova",
            model_name="sensenova-6.8-flash-lite",
            base_url="https://token.sensenova.cn/v1",
            api_key="secret",
        )
    )

    result = await adapter.health_check()

    assert result["ok"] is True
    assert result["status"] == "connected"
    assert captured["url"] == "https://token.sensenova.cn/v1/chat/completions"
    assert captured["json"]["model"] == "sensenova-6.8-flash-lite"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["client_kwargs"]["verify"] == "C:/certs/sensenova-ca.pem"


@pytest.mark.asyncio
async def test_hermes_health_check_reports_missing_credentials():
    adapter = HermesAdapter(
        model_runtime_config=ModelRuntimeConfig(
            model_config_id="model-1",
            provider="sensenova",
            model_name="sensenova-6.8-flash-lite",
            base_url="https://token.sensenova.cn/v1",
            api_key=None,
        )
    )

    result = await adapter.health_check()

    assert result == {
        "ok": False,
        "status": "unconfigured",
        "message": "Model API key is not configured.",
    }


def test_hermes_chat_command_starts_in_run_workspace(tmp_path):
    cli = HermesCliWrapper()
    cli._env["WEBAGENT_RUN_WORKSPACE"] = "/tmp/webagent-run"

    command = cli._build_chat_bash_command("hello", run_id="run-1")

    assert command.startswith("cd /tmp/webagent-run && ")


@pytest.mark.asyncio
async def test_hermes_stream_forwards_prompt_verbatim():
    captured: dict[str, object] = {}

    class FakeCli:
        last_artifact_paths: list[str] = []
        last_artifacts: list[dict] = []
        last_diagnostics: dict[str, object] = {}

        async def ask_stream_events(self, **kwargs):
            captured.update(kwargs)
            yield HermesStreamEvent(event_type="completed", content="ok")

    adapter = HermesAdapter()
    adapter.cli = FakeCli()
    content = "  请使用 sn-deep-research 调研《主题乐园》。\n\n保留这些空行。  "

    events = [
        event
        async for event in adapter.stream_response_events(
            AgentRunCreate(content=content, session_id="session_1")
        )
    ]

    assert events[0].step.label == "ok"
    assert captured["question"] == content
    assert captured["conversation_id"] == "session_1"
    assert "skills" not in captured
    assert "toolsets" not in captured


@pytest.mark.asyncio
async def test_hermes_retries_stalled_resumed_session_once_with_same_prompt():
    attempts: list[dict[str, object]] = []

    class FakeCli:
        last_artifact_paths: list[str] = []
        last_artifacts: list[dict] = []
        last_diagnostics: dict[str, object] = {}

        async def ask_stream_events(self, **kwargs):
            attempts.append(kwargs)
            if len(attempts) == 1:
                yield HermesStreamEvent(
                    event_type="tool_call",
                    content=(
                        "Stream stalled mid tool-call (write_file); "
                        "the action was not executed."
                    ),
                )
                return
            yield HermesStreamEvent(event_type="completed", content="PPTX 已生成")

    adapter = HermesAdapter(resume_session_id="damaged-session")
    adapter.cli = FakeCli()
    prompt = "生成 PPTX"

    events = [
        event
        async for event in adapter.stream_response_events(
            AgentRunCreate(content=prompt, session_id="session_1", run_id="run_1")
        )
    ]

    assert [attempt["question"] for attempt in attempts] == [prompt, prompt]
    assert [attempt["session_id"] for attempt in attempts] == ["damaged-session", None]
    assert [event.step.label for event in events] == [
        "Hermes 工具输出中断，正在使用干净会话重试一次...",
        "PPTX 已生成",
    ]


@pytest.mark.asyncio
async def test_hermes_does_not_retry_stall_after_artifact_exists():
    attempts = 0

    class FakeCli:
        last_artifact_paths = ["/tmp/report.pptx"]
        last_artifacts: list[dict] = []
        last_diagnostics: dict[str, object] = {}

        async def ask_stream_events(self, **kwargs):
            nonlocal attempts
            del kwargs
            attempts += 1
            yield HermesStreamEvent(
                event_type="tool_call",
                content=(
                    "Stream stalled mid tool-call (cleanup); "
                    "the action was not executed."
                ),
            )

    adapter = HermesAdapter(resume_session_id="session-with-artifact")
    adapter.cli = FakeCli()

    events = [
        event
        async for event in adapter.stream_response_events(
            AgentRunCreate(content="finish", session_id="session_1", run_id="run_1")
        )
    ]

    assert attempts == 1
    assert len(events) == 1


def test_final_discovery_scans_the_run_runtime_root(tmp_path):
    runtime_root = tmp_path / "runtime-run"
    hermes_home = runtime_root / "hermes-home"
    hermes_home.mkdir(parents=True)
    generated = runtime_root / "ppt_decks" / "deck" / "report.pptx"
    generated.parent.mkdir(parents=True)
    generated.write_bytes(b"pptx")

    cli = HermesCliWrapper(hermes_home=str(hermes_home))
    cli._discover_run_directory_artifacts(
        working_dir=str(tmp_path / "other-workspace"),
        artifacts_dir=None,
        started_at=datetime.now() - timedelta(seconds=5),
    )

    assert cli.last_artifact_paths == [str(generated.resolve())]
    assert cli.last_artifacts[0]["artifact_type"] == "ppt_deck"


def test_final_discovery_ignores_runtime_dependencies(tmp_path):
    runtime_root = tmp_path / "runtime-run"
    hermes_home = runtime_root / "hermes-home"
    package_license = (
        hermes_home
        / ".local"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "markdown-3.10.dist-info"
        / "licenses"
        / "LICENSE.md"
    )
    package_license.parent.mkdir(parents=True)
    package_license.write_text("dependency license", encoding="utf-8")
    generated = runtime_root / "outputs" / "report.html"
    generated.parent.mkdir(parents=True)
    generated.write_text("<html>report</html>", encoding="utf-8")

    cli = HermesCliWrapper(hermes_home=str(hermes_home))
    cli._discover_run_directory_artifacts(
        working_dir=str(runtime_root),
        artifacts_dir=None,
        started_at=datetime.now() - timedelta(seconds=5),
    )

    assert cli.last_artifact_paths == [str(generated.resolve())]
