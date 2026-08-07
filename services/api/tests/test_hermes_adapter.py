import pytest

from agent_runtime.adapters.hermes_adapter import HermesAdapter
from agent_runtime.adapters.hermes_cli import HermesCliWrapper
from agent_runtime.adapters.hermes_cli import HermesStreamEvent
from agent_runtime.schemas import AgentRunCreate


def test_hermes_adapter_has_no_skill_mapping_helpers():
    adapter = HermesAdapter()

    assert not hasattr(adapter, "_get_skills_for_skill")
    assert not hasattr(adapter, "_get_toolsets_for_skill")
    assert not hasattr(adapter, "_build_runtime_prompt")


@pytest.mark.asyncio
async def test_hermes_create_run_forwards_prompt_verbatim():
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

    run = await adapter.create_run(
        AgentRunCreate(content=content, session_id="session_1", skill_key="deep_research")
    )

    assert run.output == "ok"
    assert captured["question"] == content
    assert captured["skills"] is None
    assert captured["toolsets"] is None


def test_hermes_prompt_adds_serper_runtime_guidance(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "serper")
    monkeypatch.setenv("SERPER_API_KEY", "test-key")

    prompt = HermesCliWrapper._with_runtime_search_guidance("请调研青年消费趋势")

    assert "SEARCH_PROVIDER=serper" in prompt
    assert "Do not use terminal/curl probes" in prompt
    assert "use the configured Serper search tool directly" in prompt
    assert HermesCliWrapper._with_runtime_search_guidance(prompt) == prompt
