import pytest

from agent_runtime.adapters.openclaw_adapter import OpenClawAdapter


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
