from agent_runtime.adapters.hermes_adapter import HermesAdapter


def test_hermes_deep_research_uses_sensenova_skill_entrypoint():
    adapter = HermesAdapter()

    assert adapter._get_skills_for_skill("deep_research") == "sn-deep-research"


def test_hermes_ppt_generation_uses_workbench_skill_entrypoint():
    adapter = HermesAdapter()

    assert adapter._get_skills_for_skill("ppt_generation") == "sn-ppt-workbench"


def test_hermes_deep_research_prompt_includes_serper_runtime_note():
    prompt = HermesAdapter._build_runtime_prompt("请调研青年线下社交", "deep_research")

    assert "SEARCH_PROVIDER=serper" in prompt
    assert "Serper is configured and reachable" in prompt
    assert "Do not judge search availability" in prompt
    assert "User request:" in prompt
    assert "请调研青年线下社交" in prompt


def test_hermes_plain_chat_prompt_is_unchanged():
    content = "你好"

    assert HermesAdapter._build_runtime_prompt(content, None) == content
