import pytest

from agent_runtime.adapters.hermes_adapter import HermesAdapter
from agent_runtime.adapters.hermes_cli import HermesCliWrapper, HermesStreamEvent
from agent_runtime.schemas import AgentRunCreate


def test_hermes_adapter_has_no_skill_mapping_helpers():
    adapter = HermesAdapter()

    assert not hasattr(adapter, "_get_skills_for_skill")
    assert not hasattr(adapter, "_get_toolsets_for_skill")
    assert not hasattr(adapter, "_build_runtime_prompt")


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
    content = "请使用 sn-deep-research 调研《主题乐园》并输出 Markdown 报告。"

    events = [
        event
        async for event in adapter.stream_response_events(
            AgentRunCreate(content=content, session_id="session_1")
        )
    ]

    assert events[0].step.label == "ok"
    assert captured["question"] == content
    assert "skills" not in captured
    assert "toolsets" not in captured
