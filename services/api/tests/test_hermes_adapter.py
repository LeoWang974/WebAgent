from agent_runtime.adapters.hermes_adapter import HermesAdapter


def test_hermes_deep_research_uses_sensenova_skill_entrypoint():
    adapter = HermesAdapter()

    assert adapter._get_skills_for_skill("deep_research") == "sn-deep-research"


def test_hermes_ppt_generation_uses_workbench_skill_entrypoint():
    adapter = HermesAdapter()

    assert adapter._get_skills_for_skill("ppt_generation") == "sn-ppt-workbench"


def test_hermes_deep_research_prompt_is_unchanged():
    content = "请调研青年线下社交"

    assert HermesAdapter._build_runtime_prompt(content, "deep_research") == content


def test_hermes_serper_prompt_is_unchanged():
    content = "请使用 Serper 搜索资料"

    assert HermesAdapter._build_runtime_prompt(content, None) == content


def test_hermes_plain_chat_prompt_is_unchanged():
    content = "你好"

    assert HermesAdapter._build_runtime_prompt(content, None) == content
