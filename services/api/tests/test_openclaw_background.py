import pytest

from agent_runtime.adapters.openclaw_adapter import OpenClawAdapter
from agent_runtime.adapters.openclaw_utils import (
    OPENCLAW_EVENT_PROTOCOL,
)
from agent_runtime.schemas import AgentRunCreate


def test_openclaw_adapter_uses_longer_background_timeout_for_html_generation():
    adapter = OpenClawAdapter(agent_id="main", command_timeout_seconds=30)

    assert adapter._background_wait_timeout_seconds("html_generation") == 30 * 60


def test_openclaw_adapter_waits_for_background_long_skill():
    input_data = AgentRunCreate(
        content="Output Chinese Markdown report",
        session_id="session_123",
        run_id="run_123",
        skill_key="deep_research",
    )

    assert OpenClawAdapter._should_wait_for_background_completion(
        input_data,
        "Starting deep research workflow. Step 1: create report directory and dispatch scout.",
    )
    assert not OpenClawAdapter._should_wait_for_background_completion(
        input_data,
        "Report generated: /home/demo/report.md",
    )


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
        content="璇蜂娇鐢ㄤ笂杩扮敓鎴愮殑銆婂煄甯傚缁忔祹鏂版満浼氥€媘arkdown鎶ュ憡銆備娇鐢╮eport-html-v2涓烘垜杈撳嚭HTML鏂囦欢",
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
            "璇蜂娇鐢ㄤ笂杩扮敓鎴愮殑銆婂煄甯傚缁忔祹鏂版満浼氥€媘arkdown鎶ュ憡銆備娇鐢╮eport-html-v2"
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
            "璇蜂娇鐢ㄤ箣鍓嶇敓鎴愮殑銆婁簩娆″厓姝ｅ湪鏀瑰彉娑堣垂甯傚満銆媘arkdown鎶ュ憡銆備娇鐢╮eport-html-v2"
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
        content="璇蜂娇鐢ㄤ笂杩扮敓鎴愮殑銆婂煄甯傚缁忔祹鏂版満浼氥€媘arkdown鎶ュ憡銆備娇鐢╮eport-html-v2涓烘垜杈撳嚭HTML鏂囦欢",
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
            "璇蜂娇鐢ㄤ笂杩扮敓鎴愮殑銆婂煄甯傚缁忔祹鏂版満浼氥€媘arkdown鎶ュ憡銆備娇鐢╮eport-html-v2"
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
            "璇蜂娇鐢ㄤ笂杩扮敓鎴愮殑銆婂煄甯傚缁忔祹鏂版満浼氥€媘arkdown鎶ュ憡銆備娇鐢╮eport-html-v2"
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
            "[User request]\nconvenience store war"
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
        "task": "webagent_skill=deep_research\n[User request]\nconvenience store war",
        "status": "succeeded",
    }
    child_task = {
        "taskId": "child-task",
        "runtime": "subagent",
        "sourceId": "openclaw-run-1",
        "runId": "openclaw-run-1",
        "task": (
            "dimension_id:d4\n"
            "dimension_name:supply chain and instant retail\n"
            f"report_dir:{report_dir}"
        ),
        "status": "running",
    }

    matched = adapter._matching_task_family([main_task, child_task], input_data, set())

    assert matched == [main_task, child_task]
    assert adapter._summarize_task_label(child_task) == "OpenClaw is researching d4."


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


@pytest.mark.asyncio
async def test_openclaw_adapter_emits_protocol_events_and_artifacts(monkeypatch):
    adapter = OpenClawAdapter()
    input_data = AgentRunCreate(
        content=(
            "Use sn-deep-research to research convenience store competition "
            "and output Markdown"
        ),
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
                "label": "Searching convenience store fresh food cases",
                "progress": 32,
            },
            {
                "protocol": OPENCLAW_EVENT_PROTOCOL,
                "event_type": "artifact_found",
                "label": "Report generated",
                "artifact_paths": [
                    "/home/demo/.openclaw/workspace/reports/topic/report.md"
                ],
                "artifact_type": "markdown_report",
                "source_dir": "/home/demo/.openclaw/workspace/reports/topic",
                "title": "Convenience store fresh food report",
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
    assert protocol_events[0].step.label == "Searching convenience store fresh food cases"
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
        content="璇疯緭鍑轰腑鏂?Markdown 鎶ュ憡",
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
        lambda task, skill_key=None: (
            "OpenClaw is researching report and collecting report artifacts."
        ),
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
