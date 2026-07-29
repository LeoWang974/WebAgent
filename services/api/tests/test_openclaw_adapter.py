import os
from pathlib import Path

import pytest

from agent_runtime.adapters.openclaw_adapter import OpenClawAdapter
from agent_runtime.adapters.openclaw_utils import (
    OPENCLAW_EVENT_PROTOCOL,
    artifact_to_payload,
    extract_output,
    extract_protocol_events,
    extract_structured_artifact_paths,
    extract_structured_artifacts,
)
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
        content="请使用 report.md，使用report-html-v2输出HTML文件",
        session_id="session_123",
        run_id="run_123",
        skill_key="html_generation",
    )

    message = adapter._build_openclaw_message(input_data)

    assert message == "请使用 report.md，使用report-html-v2输出HTML文件"
    assert "webagent_skill=html_generation" not in message
    assert "report-html-v2 workflow" not in message


def test_openclaw_adapter_uses_longer_background_timeout_for_html_generation():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30)

    assert adapter._background_wait_timeout_seconds("html_generation") == 30 * 60


def test_openclaw_adapter_leaves_plain_chat_prompt_unchanged():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30)
    input_data = AgentRunCreate(content="你好", session_id="session_123", run_id="run_123")

    assert adapter._build_openclaw_message(input_data) == "你好"


def test_openclaw_adapter_extracts_json_output():
    output = extract_output(
        '{"reply":"OpenClaw connected"}',
        "",
    )

    assert output == "OpenClaw connected"


def test_openclaw_adapter_extracts_payload_text_from_stderr_json():
    output = extract_output(
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


def test_openclaw_adapter_extracts_standard_protocol_events():
    payload = {
        "taskId": "task-main",
        "status": "running",
        "events": [
            {
                "protocol": OPENCLAW_EVENT_PROTOCOL,
                "event_type": "tool_call",
                "label": "正在检索便利店鲜食案例",
                "progress": 32,
            },
            {
                "protocol": OPENCLAW_EVENT_PROTOCOL,
                "event_type": "artifact_found",
                "label": "报告已生成",
                "artifact_paths": [
                    "/home/demo/.openclaw/workspace/reports/topic/report.md"
                ],
                "artifact_type": "markdown_report",
                "source_dir": "/home/demo/.openclaw/workspace/reports/topic",
                "title": "便利店鲜食报告",
                "progress": 90,
            },
        ],
    }

    events = extract_protocol_events(payload)

    assert [event["event_type"] for event in events] == [
        "tool_call",
        "artifact_found",
    ]
    assert events[0]["label"] == "正在检索便利店鲜食案例"
    assert events[0]["source"]["taskId"] == "task-main"
    artifacts = events[1]["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0].path.endswith("/report.md")
    assert artifacts[0].artifact_type == "markdown_report"


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
    output = extract_output(
        '{"runId":"run_1","status":"ok","result":{"payloads":[{"text":"gateway connected"}]}}',
        "",
    )

    assert output == "gateway connected"


def test_openclaw_adapter_cleans_text_output_and_skips_warnings():
    output = extract_output(
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
    paths = extract_structured_artifact_paths(
        "",
        '{"payloads":[{"text":"done","mediaUrl":"/mnt/c/Users/demo/image.png"}],'
        '"artifact_paths":["/mnt/c/Users/demo/report.md"]}',
    )

    assert paths == ["/mnt/c/Users/demo/report.md", "/mnt/c/Users/demo/image.png"]


def test_openclaw_adapter_extracts_structured_artifact_refs():
    refs = extract_structured_artifacts(
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
    payload = artifact_to_payload(
        extract_structured_artifacts(
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


def test_openclaw_adapter_ppt_primary_output_ignores_source_markdown():
    adapter = OpenClawAdapter()
    adapter._remember_artifact_paths(
        "Use C:\\Users\\demo\\Downloads\\report.md and generated "
        "C:\\Users\\demo\\Downloads\\deck.pptx"
    )

    assert adapter._primary_output_artifact_paths("ppt_generation") == [
        "C:\\Users\\demo\\Downloads\\deck.pptx"
    ]


def test_openclaw_adapter_extracts_windows_input_parent_dirs():
    dirs = OpenClawAdapter._extract_file_parent_dirs(
        "C:\\Users\\demo\\Downloads\\report-50ffa786ad.md报告，生成PPT"
    )

    assert "/mnt/c/Users/demo/Downloads" in dirs


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


def test_openclaw_adapter_treats_ppt_html_generator_failure_as_recoverable():
    assert OpenClawAdapter._is_recoverable_failed_task(
        "ppt_generation",
        "html-generator",
    )
    assert not OpenClawAdapter._is_recoverable_failed_task(
        "deep_research",
        "html-generator",
    )


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


def test_openclaw_adapter_remembers_run_task_ids():
    adapter = OpenClawAdapter()

    adapter._remember_run_task_ids(
        "run_123",
        [
            {"taskId": "task-main", "status": "running"},
            {"taskId": "task-child", "status": "queued"},
            {"taskId": None, "status": "running"},
        ],
    )

    assert adapter.run_task_ids["run_123"] == {"task-main", "task-child"}


@pytest.mark.asyncio
async def test_openclaw_adapter_cancels_cached_and_matching_gateway_tasks(monkeypatch):
    adapter = OpenClawAdapter()
    adapter.run_task_ids["run_123"] = {"cached-task"}
    cancelled = []

    async def fake_json_command(args, timeout_seconds=20):
        assert args == ["tasks", "list", "--json"]
        return {
            "tasks": [
                {
                    "taskId": "matching-task",
                    "status": "running",
                    "task": "webagent_run_id=run_123\nresearch",
                },
                {
                    "taskId": "old-task",
                    "status": "running",
                    "task": "webagent_run_id=old_run\nresearch",
                },
            ]
        }

    async def fake_command(args, timeout_seconds=20):
        cancelled.append(args)
        return 0, "", ""

    monkeypatch.setattr(adapter, "_run_openclaw_json_command", fake_json_command)
    monkeypatch.setattr(adapter, "_run_openclaw_command", fake_command)

    await adapter._cancel_openclaw_tasks("run_123")

    assert cancelled == [
        ["tasks", "cancel", "cached-task"],
        ["tasks", "cancel", "matching-task"],
    ]
    assert "run_123" not in adapter.run_task_ids


@pytest.mark.asyncio
async def test_openclaw_adapter_emits_protocol_events_and_artifacts(monkeypatch):
    adapter = OpenClawAdapter()
    input_data = AgentRunCreate(
        content="请使用 sn-deep-research 调研《便利店战争》，输出中文 Markdown 报告",
        session_id="session_123",
        run_id="run_123",
        skill_key="deep_research",
    )
    task = {
        "taskId": "task-main",
        "runtime": "cli",
        "status": "running",
        "task": "webagent_skill=deep_research\nwebagent_run_id=run_123\n",
        "events": [
            {
                "protocol": OPENCLAW_EVENT_PROTOCOL,
                "event_type": "tool_call",
                "label": "正在检索便利店鲜食案例",
                "progress": 32,
            },
            {
                "protocol": OPENCLAW_EVENT_PROTOCOL,
                "event_type": "artifact_found",
                "label": "报告已生成",
                "artifact_paths": [
                    "/home/demo/.openclaw/workspace/reports/topic/report.md"
                ],
                "artifact_type": "markdown_report",
                "source_dir": "/home/demo/.openclaw/workspace/reports/topic",
                "title": "便利店鲜食报告",
                "progress": 90,
                "status": "completed",
            },
        ],
    }
    poll_state = {
        "last_label": "",
        "last_artifact_count": 0,
        "last_visible_emit_at": 0.0,
        "progress": 20,
        "recoverable_failure_reported": False,
    }

    async def fake_json_command(args, timeout_seconds=20):
        return {"tasks": [task]}

    async def fake_find_report_artifacts(report_dirs):
        return []

    async def fake_discover_report_dirs(input_data):
        return set()

    monkeypatch.setattr(adapter, "_run_openclaw_json_command", fake_json_command)
    monkeypatch.setattr(adapter, "_find_report_artifacts", fake_find_report_artifacts)
    monkeypatch.setattr(adapter, "_discover_report_dirs_from_input", fake_discover_report_dirs)

    events = await adapter._poll_task_family_snapshot(
        input_data,
        "run_123",
        set(),
        poll_state,
    )

    protocol_events = [
        event
        for event in events
        if event.payload.get("protocol") == OPENCLAW_EVENT_PROTOCOL
    ]
    assert [event.event_type for event in protocol_events] == [
        "tool_call",
        "artifact_found",
    ]
    assert protocol_events[0].step.label == "正在检索便利店鲜食案例"
    assert protocol_events[1].step.status == "completed"
    assert adapter.get_last_artifact_paths() == [
        "/home/demo/.openclaw/workspace/reports/topic/report.md"
    ]
    assert adapter._primary_output_artifact_paths("deep_research") == [
        "/home/demo/.openclaw/workspace/reports/topic/report.md"
    ]


@pytest.mark.asyncio
async def test_openclaw_adapter_emits_visible_heartbeat_for_unchanged_running_task(monkeypatch):
    adapter = OpenClawAdapter()
    input_data = AgentRunCreate(
        content="请输出中文 Markdown 报告",
        session_id="session_123",
        run_id="run_123",
        skill_key="deep_research",
    )
    task = {
        "taskId": "task-main",
        "runtime": "cli",
        "status": "running",
        "task": "webagent_skill=deep_research\nwebagent_run_id=run_123\n",
    }
    poll_state = {
        "last_label": "OpenClaw is researching report and collecting report artifacts.",
        "last_artifact_count": 0,
        "last_visible_emit_at": 0.0,
        "progress": 28,
        "recoverable_failure_reported": False,
    }

    async def fake_json_command(args, timeout_seconds=20):
        return {"tasks": [task]}

    async def fake_find_report_artifacts(report_dirs):
        return []

    async def fake_discover_report_dirs(input_data):
        return set()

    monkeypatch.setattr(adapter, "_run_openclaw_json_command", fake_json_command)
    monkeypatch.setattr(adapter, "_find_report_artifacts", fake_find_report_artifacts)
    monkeypatch.setattr(adapter, "_discover_report_dirs_from_input", fake_discover_report_dirs)
    monkeypatch.setattr(
        adapter,
        "_summarize_task_label",
        lambda task: "OpenClaw is researching report and collecting report artifacts.",
    )

    events = await adapter._poll_task_family_snapshot(
        input_data,
        "run_123",
        set(),
        poll_state,
    )

    assert len(events) == 1
    assert events[0].step
    assert events[0].step.label.startswith("OpenClaw 长任务仍在执行")
