import os
from pathlib import Path

import pytest
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
        assert args[:2] == ["openclaw", "agent"]
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


def test_openclaw_adapter_injects_default_skills_dir_for_wsl_commands():
    command = OpenClawAdapter._with_runtime_env(
        "openclaw health",
        {"OPENCLAW_SKILLS_DIR": "/mnt/d/WebAgent/runtime/openclaw-skills"},
    )

    assert "OPENCLAW_SKILLS_DIR=${OPENCLAW_SKILLS_DIR:-" in command
    assert "/mnt/d/WebAgent/runtime/openclaw-skills" in command
    assert command.endswith("openclaw health")


def test_openclaw_adapter_can_build_local_cli_args():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30, mode="local_cli")

    args = adapter._build_agent_cli_args(
        AgentRunCreate(content="hello", session_id="session_123", run_id="run_123")
    )

    assert "--local" in " ".join(args)


def test_openclaw_adapter_maps_webagent_skill_to_openclaw_prompt():
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

    assert "webagent_skill=ppt_generation" in message
    assert "openclaw_capability=presentation" in message
    assert "artifact_paths, artifact_type, source_dir, run_id, and title" in message
    assert "请生成《未来餐桌》PPT" in message
    assert "openclaw_capability=presentation" in joined


def test_openclaw_adapter_maps_html_generation_to_report_html_prompt():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30)
    input_data = AgentRunCreate(
        content="请使用 report.md，使用report-html-v2输出HTML文件",
        session_id="session_123",
        run_id="run_123",
        skill_key="html_generation",
    )

    message = adapter._build_openclaw_message(input_data)

    assert "webagent_skill=html_generation" in message
    assert "openclaw_capability=html_report_generation" in message
    assert "report-html-v2 workflow" in message
    assert "Expected artifact_type: html_page" in message


def test_openclaw_adapter_uses_longer_background_timeout_for_html_generation():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30)

    assert adapter._background_wait_timeout_seconds("html_generation") == 30 * 60


def test_openclaw_adapter_leaves_plain_chat_prompt_unchanged():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30)
    input_data = AgentRunCreate(content="你好", session_id="session_123", run_id="run_123")

    assert adapter._build_openclaw_message(input_data) == "你好"


def test_openclaw_adapter_extracts_json_output():
    output = OpenClawAdapter._extract_output(
        '{"reply":"OpenClaw connected"}',
        "",
    )

    assert output == "OpenClaw connected"


def test_openclaw_adapter_extracts_payload_text_from_stderr_json():
    output = OpenClawAdapter._extract_output(
        "",
        '{"payloads":[{"text":"connected","mediaUrl":null}],"meta":{"durationMs":10}}',
    )

    assert output == "connected"


def test_openclaw_adapter_reads_json_from_stderr_bytes():
    payload = OpenClawAdapter._first_json_like_text(
        b"",
        b'{"tasks":[{"status":"succeeded"}]}',
    )

    assert payload == '{"tasks":[{"status":"succeeded"}]}'


def test_openclaw_adapter_ignores_auxiliary_markdown_as_primary_artifacts():
    assert not OpenClawAdapter._is_primary_output_artifact(
        "/home/demo/deep-research-reports/topic/request.md"
    )
    assert not OpenClawAdapter._is_primary_output_artifact(
        "/home/demo/deep-research-reports/topic/synthesis.md"
    )
    assert not OpenClawAdapter._is_primary_output_artifact(
        "/home/demo/deep-research-reports/topic/sub_reports/d1.md"
    )
    assert OpenClawAdapter._is_primary_output_artifact(
        "/home/demo/deep-research-reports/topic/report.md"
    )


def test_openclaw_adapter_extracts_report_dir_search_needles():
    needles = OpenClawAdapter._report_dir_search_needles(
        "请使用 sn-deep-research 调研《城市夜经济新机会》，输出中文Markdown 报告"
    )

    assert "城市夜经济新机会" in needles


def test_openclaw_adapter_extracts_gateway_result_payload_text():
    output = OpenClawAdapter._extract_output(
        '{"runId":"run_1","status":"ok","result":{"payloads":[{"text":"gateway connected"}]}}',
        "",
    )

    assert output == "gateway connected"


def test_openclaw_adapter_cleans_text_output_and_skips_warnings():
    output = OpenClawAdapter._extract_output(
        "OpenClaw\n\x1b[36m[skills]\x1b[39m Skipping path\n",
        "",
    )

    assert output == "OpenClaw"


def test_openclaw_adapter_extracts_artifact_refs():
    adapter = OpenClawAdapter()

    adapter._remember_artifact_paths(
        "Generated /mnt/c/Users/demo/report.md and C:\\Users\\demo\\deck.pptx"
    )

    artifacts = adapter.get_last_artifacts()
    assert adapter.get_last_artifact_paths() == [
        "/mnt/c/Users/demo/report.md",
        "C:\\Users\\demo\\deck.pptx",
    ]
    assert artifacts[0].artifact_type == "markdown_report"
    assert artifacts[0].source_dir
    assert artifacts[0].title == "report"
    assert artifacts[1].artifact_type == "ppt_deck"


def test_openclaw_adapter_extracts_structured_artifact_paths():
    paths = OpenClawAdapter._extract_structured_artifact_paths(
        "",
        '{"payloads":[{"text":"done","mediaUrl":"/mnt/c/Users/demo/image.png"}],'
        '"artifact_paths":["/mnt/c/Users/demo/report.md"]}',
    )

    assert paths == ["/mnt/c/Users/demo/report.md", "/mnt/c/Users/demo/image.png"]


def test_openclaw_adapter_extracts_structured_artifact_refs():
    refs = OpenClawAdapter._extract_structured_artifacts(
        "",
        (
            '{"run_id":"openclaw_run_1","source_dir":"/mnt/c/Users/demo/output",'
            '"artifacts":[{"artifact_paths":["/mnt/c/Users/demo/output/report.md"],'
            '"artifact_type":"markdown_report","title":"Market Report"}]}'
        ),
    )

    assert len(refs) == 1
    assert refs[0].path == "/mnt/c/Users/demo/output/report.md"
    assert refs[0].artifact_type == "markdown_report"
    assert refs[0].source_dir == "/mnt/c/Users/demo/output"
    assert refs[0].run_id == "openclaw_run_1"
    assert refs[0].title == "Market Report"


def test_openclaw_adapter_artifact_payload_uses_standard_protocol_fields():
    payload = OpenClawAdapter._artifact_to_payload(
        OpenClawAdapter._extract_structured_artifacts(
            "",
            (
                '{"artifact_path":"/mnt/c/Users/demo/output/chart.png",'
                '"artifact_type":"image_result","source_dir":"/mnt/c/Users/demo/output",'
                '"run_id":"openclaw_run_2","title":"Chart"}'
            ),
        )[0]
    )

    assert payload == {
        "artifact_paths": ["/mnt/c/Users/demo/output/chart.png"],
        "artifact_path": "/mnt/c/Users/demo/output/chart.png",
        "artifact_type": "image_result",
        "run_id": "openclaw_run_2",
        "source_dir": "/mnt/c/Users/demo/output",
        "title": "Chart",
    }


def test_openclaw_adapter_waits_for_background_long_skill():
    input_data = AgentRunCreate(
        content="输出中文 Markdown 报告",
        session_id="session_123",
        run_id="run_123",
        skill_key="deep_research",
    )

    assert OpenClawAdapter._should_wait_for_background_completion(
        input_data,
        "好的，开始启动深度研究流程。\n\n第一步：创建报告目录 + 派发 scout 预检",
    )
    assert not OpenClawAdapter._should_wait_for_background_completion(
        input_data,
        "报告已生成：/home/demo/report.md",
    )


def test_openclaw_adapter_primary_output_excludes_debug_json():
    assert not OpenClawAdapter._is_primary_output_artifact("/home/demo/briefing.json")
    assert not OpenClawAdapter._is_primary_output_artifact(
        "/home/demo/deep-research-reports/topic/sub_reports/d3-subreport.md"
    )
    assert OpenClawAdapter._is_primary_output_artifact("/home/demo/report.md")


def test_openclaw_adapter_uses_longer_background_timeout_for_deep_research():
    adapter = OpenClawAdapter(command_timeout_seconds=600)

    assert adapter._background_wait_timeout_seconds("deep_research") == 45 * 60
    assert adapter._background_wait_timeout_seconds(None) == 600


def test_openclaw_adapter_ignores_recoverable_timed_out_background_text():
    label = OpenClawAdapter._failed_background_task_label(
        [
            {
                "label": "research-d4-virtual",
                "status": "running",
                "task": "task: research-d4-virtual\nstatus: timed out\n",
            }
        ]
    )

    assert label is None


def test_openclaw_adapter_detects_failed_background_task_status():
    label = OpenClawAdapter._failed_background_task_label(
        [
            {
                "label": "research-d4-virtual",
                "status": "timed_out",
                "task": "task: research-d4-virtual\n",
            }
        ]
    )

    assert label == "research-d4-virtual"


def test_openclaw_adapter_does_not_match_old_failed_task_by_skill_only():
    adapter = OpenClawAdapter()
    input_data = AgentRunCreate(
        content="请使用上述生成的《城市夜经济新机会》markdown报告。使用report-html-v2为我输出HTML文件",
        session_id="session_123",
        run_id="run_123",
        skill_key="html_generation",
    )
    current_task = {
        "taskId": "current-task",
        "runtime": "cli",
        "sourceId": "current-run",
        "runId": "current-run",
        "task": (
            "webagent_skill=html_generation\n"
            "请使用上述生成的《城市夜经济新机会》markdown报告。使用report-html-v2"
        ),
        "status": "running",
    }
    old_failed_task = {
        "taskId": "old-task",
        "runtime": "cli",
        "sourceId": "old-run",
        "runId": "old-run",
        "task": (
            "webagent_skill=html_generation\n"
            "请使用之前生成的《二次元正在改变消费市场》markdown报告。使用report-html-v2"
        ),
        "status": "timed_out",
    }

    matched = adapter._matching_task_family(
        [old_failed_task, current_task],
        input_data,
        set(),
    )

    assert matched == [current_task]


def test_openclaw_adapter_prefers_current_webagent_run_id_when_present():
    adapter = OpenClawAdapter()
    input_data = AgentRunCreate(
        content="请使用上述生成的《城市夜经济新机会》markdown报告。使用report-html-v2为我输出HTML文件",
        session_id="session_123",
        run_id="new_run",
        skill_key="html_generation",
    )
    old_same_prompt_task = {
        "taskId": "old-task",
        "runtime": "cli",
        "sourceId": "old-run",
        "runId": "old-run",
        "task": (
            "webagent_skill=html_generation\nwebagent_run_id=old_run\n"
            "请使用上述生成的《城市夜经济新机会》markdown报告。使用report-html-v2"
        ),
        "status": "running",
    }
    current_task = {
        "taskId": "current-task",
        "runtime": "cli",
        "sourceId": "current-run",
        "runId": "current-run",
        "task": (
            "webagent_skill=html_generation\nwebagent_run_id=new_run\n"
            "请使用上述生成的《城市夜经济新机会》markdown报告。使用report-html-v2"
        ),
        "status": "running",
    }

    matched = adapter._matching_task_family(
        [old_same_prompt_task, current_task],
        input_data,
        set(),
    )

    assert matched == [current_task]


def test_openclaw_adapter_matches_task_family_by_report_dir():
    adapter = OpenClawAdapter()
    report_dir = "/home/demo/deep-research-reports/convenience-store-war"
    input_data = AgentRunCreate(
        content=(
            "[WebAgent skill mapping]\nwebagent_skill=deep_research\n"
            "[User request]\n便利店战争"
        ),
        session_id="session_123",
        run_id="run_123",
        skill_key="deep_research",
    )
    main_task = {
        "taskId": "main-task",
        "runtime": "cli",
        "sourceId": "openclaw-run-1",
        "runId": "openclaw-run-1",
        "task": "webagent_skill=deep_research\n[User request]\n便利店战争",
        "status": "succeeded",
    }
    child_task = {
        "taskId": "child-task",
        "runtime": "subagent",
        "sourceId": "openclaw-run-1",
        "runId": "openclaw-run-1",
        "task": f"dimension_id:d4\n维度名称:供应链与即时零售\nreport_dir:{report_dir}",
        "status": "running",
    }

    matched = adapter._matching_task_family([main_task, child_task], input_data, set())

    assert matched == [main_task, child_task]
    assert adapter._summarize_task_label(child_task) == (
        "OpenClaw is researching d4: 供应链与即时零售"
    )


@pytest.mark.asyncio
async def test_openclaw_adapter_polls_background_after_cli_timeout(monkeypatch):
    class TimeoutProcess:
        returncode = None
        killed = False

        async def communicate(self):
            if self.killed:
                return b"", b""
            raise TimeoutError

        def kill(self):
            self.killed = True
            self.returncode = -9

    adapter = OpenClawAdapter(command_timeout_seconds=1)
    process = TimeoutProcess()
    seen = []

    async def fake_start(input_data, run_id):
        return process

    async def fake_poll(input_data, run_id, initial_output, report_dirs=None, poll_state=None):
        seen.append((run_id, initial_output))
        yield adapter._stage_event(run_id, "stage_update", "background polled", 50)

    monkeypatch.setattr(adapter, "_start_agent_process", fake_start)
    monkeypatch.setattr(adapter, "_poll_background_completion", fake_poll)

    events = [
        event
        async for event in adapter.stream_response_events(
            AgentRunCreate(
                content="long research",
                session_id="session_123",
                run_id="run_123",
                skill_key="deep_research",
            )
        )
    ]

    assert seen == [("run_123", "long research")]
    assert any(event.step and event.step.label == "background polled" for event in events)
    assert adapter.get_last_diagnostics()["cliTimedOut"] is True


def test_openclaw_adapter_skips_bootstrap_artifact_refs():
    adapter = OpenClawAdapter()

    adapter._remember_artifact_paths(
        "Loaded /home/demo/.openclaw/workspace/AGENTS.md and generated "
        "/home/demo/.openclaw/workspace/report.md"
    )

    assert adapter.get_last_artifact_paths() == ["/home/demo/.openclaw/workspace/report.md"]


def test_openclaw_adapter_creates_fallback_markdown_artifact(tmp_path, monkeypatch):
    adapter = OpenClawAdapter()
    monkeypatch.setattr(
        "agent_runtime.adapters.openclaw_adapter.Path.resolve",
        lambda self: tmp_path
        / "services"
        / "agent-runtime"
        / "agent_runtime"
        / "adapters"
        / "openclaw_adapter.py",
    )
    content = "# 全球主题乐园竞争格局\n\n" + "迪士尼、环球影城、方特、长隆的商业模式分析。\n" * 4

    adapter._create_fallback_artifact_from_output(
        AgentRunCreate(
            content="输出中文 Markdown 报告",
            session_id="session_123",
            run_id="run_123",
            skill_key="deep_research",
        ),
        "run_123",
        content,
    )

    artifacts = adapter.get_last_artifacts()
    assert len(artifacts) == 1
    assert artifacts[0].artifact_type == "markdown_report"
    assert artifacts[0].run_id == "run_123"
    assert Path(artifacts[0].path).read_text(encoding="utf-8") == content.strip()
