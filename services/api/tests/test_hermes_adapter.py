import pytest

from agent_runtime.adapters.hermes_adapter import HermesAdapter
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
        async def ask(self, **kwargs):
            captured.update(kwargs)
            return "session_1", "ok"

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
