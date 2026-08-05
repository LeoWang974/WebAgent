import os

from agent_runtime.adapters import openclaw_adapter
from agent_runtime.adapters.openclaw_adapter import OpenClawAdapter
from agent_runtime.schemas import AgentRunCreate


def test_openclaw_adapter_builds_gateway_cli_args():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30)
    input_data = AgentRunCreate(
        content="hello",
        session_id="session_123",
        run_id="run_123",
    )

    args = adapter._build_agent_cli_args(input_data)

    if os.name == "nt":
        assert args[:4] == ["wsl.exe", "--", "bash", "-lc"]
        assert "openclaw agent" in args[4]
    else:
        assert args[:2] == ["bash", "-lc"]
        assert "openclaw agent" in args[2]
    joined = " ".join(args)
    assert "--local" not in joined
    assert "--agent" in joined
    assert "main" in joined
    assert "--message" in joined
    assert "hello" in joined
    assert "--session-id" in joined
    assert "session_123" in joined
    if os.name == "nt":
        assert "~/.hermes/.env" in joined
        assert "~/.openclaw/.env" in joined


def test_openclaw_adapter_builds_posix_cli_with_runtime_env(monkeypatch):
    monkeypatch.setattr(openclaw_adapter.os, "name", "posix")
    adapter = OpenClawAdapter(
        agent_id="main",
        command_timeout_seconds=30,
        home_dir="/tmp/webagent-runtime/openclaw-home",
        skills_dir="/tmp/webagent-runtime/skills",
    )

    args = adapter._build_agent_cli_args(
        AgentRunCreate(content="hello", session_id="session_123", run_id="run_123")
    )

    assert args[:2] == ["bash", "-lc"]
    command = args[2]
    assert "openclaw agent" in command
    assert "export HOME=/tmp/webagent-runtime/openclaw-home" in command
    assert "export OPENCLAW_HOME=/tmp/webagent-runtime/openclaw-home" in command
    assert "export OPENCLAW_SKILLS_DIR=/tmp/webagent-runtime/skills" in command
    assert "export WEBAGENT_AGENT_CWD=/tmp/webagent-runtime/artifacts" in command
    assert "mkdir -p /tmp/webagent-runtime/artifacts" in command
    assert "cd /tmp/webagent-runtime/artifacts" in command
    assert "~/.openclaw/.env" in command
    assert "unset OPENCLAW_BASE_URL OPENCLAW_GATEWAY_URL;" in command


def test_openclaw_adapter_injects_default_skills_dir_for_wsl_commands():
    command = OpenClawAdapter._with_runtime_env(
        "openclaw health",
        {"OPENCLAW_SKILLS_DIR": "/mnt/d/WebAgent/runtime/openclaw-skills"},
    )

    assert "export OPENCLAW_SKILLS_DIR=/mnt/d/WebAgent/runtime/openclaw-skills" in command
    assert "/mnt/d/WebAgent/runtime/openclaw-skills" in command
    assert command.endswith("openclaw health")


def test_openclaw_adapter_can_build_local_cli_args():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30, mode="local_cli")

    args = adapter._build_agent_cli_args(
        AgentRunCreate(content="hello", session_id="session_123", run_id="run_123")
    )

    assert "--local" in " ".join(args)


def test_openclaw_adapter_keeps_skill_prompt_unchanged():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30)
    input_data = AgentRunCreate(
        content="请生成《未来餐桌》PPT",
        session_id="session_123",
        run_id="run_123",
        skill_key="ppt_generation",
    )

    message = adapter._build_openclaw_message(input_data)
    args = adapter._build_agent_cli_args(input_data)
    joined = " ".join(args)

    assert message == "请生成《未来餐桌》PPT"
    assert "webagent_skill=ppt_generation" not in joined
    assert "openclaw_capability=presentation" not in joined


def test_openclaw_adapter_keeps_html_generation_prompt_unchanged():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30)
    input_data = AgentRunCreate(
        content="请使用 report.md，使用 report-html-v2 输出 HTML 文件",
        session_id="session_123",
        run_id="run_123",
        skill_key="html_generation",
    )

    message = adapter._build_openclaw_message(input_data)

    assert message == "请使用 report.md，使用 report-html-v2 输出 HTML 文件"
    assert "webagent_skill=html_generation" not in message
    assert "report-html-v2 workflow" not in message


def test_openclaw_adapter_leaves_plain_chat_prompt_unchanged():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30)
    input_data = AgentRunCreate(content="你好", session_id="session_123", run_id="run_123")

    assert adapter._build_openclaw_message(input_data) == "你好"
