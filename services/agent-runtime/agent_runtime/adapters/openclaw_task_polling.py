from pathlib import Path
from time import monotonic
from typing import Any

from ..schemas import AgentRunCreate, AgentRunEvent, AgentRunStep
from .openclaw_utils import artifact_to_payload, now_iso


async def poll_task_family_snapshot(
    adapter: Any,
    input_data: AgentRunCreate,
    run_id: str,
    report_dirs: set[str],
    poll_state: dict[str, object],
) -> list[AgentRunEvent]:
    events: list[AgentRunEvent] = []
    artifact_filter_key = adapter._artifact_filter_key(input_data)
    tasks_payload = await adapter._run_openclaw_json_command(
        ["tasks", "list", "--json"],
        timeout_seconds=20,
    )
    tasks = []
    if isinstance(tasks_payload, dict):
        raw_tasks = tasks_payload.get("tasks")
        tasks = raw_tasks if isinstance(raw_tasks, list) else []

    matching_tasks = adapter._matching_task_family(
        [task for task in tasks if isinstance(task, dict)],
        input_data,
        report_dirs,
    )
    adapter._remember_run_task_ids(run_id, matching_tasks)
    for task in matching_tasks:
        task_text = adapter._task_text(task)
        report_dirs.update(adapter._extract_report_dirs(task_text))
        report_dirs.update(adapter._extract_file_parent_dirs(task_text))
        adapter._remember_structured_artifacts_from_value(task, run_id)

    events.extend(adapter._protocol_events_from_tasks(run_id, matching_tasks, poll_state))

    if not adapter._primary_output_artifact_paths(artifact_filter_key):
        report_dirs.update(await adapter._discover_report_dirs_from_input(input_data))

    artifact_paths = await adapter._find_report_artifacts(report_dirs)
    if not artifact_paths and not adapter._primary_output_artifact_paths(artifact_filter_key):
        artifact_paths = await adapter._find_recent_openclaw_artifacts(
            artifact_filter_key,
            input_data,
        )
    for path in artifact_paths:
        adapter._remember_artifact_path(path)

    failed_task_label = adapter._failed_background_task_label(matching_tasks)
    if failed_task_label and not adapter._primary_output_artifact_paths(artifact_filter_key):
        if adapter._is_recoverable_failed_task(artifact_filter_key, failed_task_label):
            if not bool(poll_state.get("recoverable_failure_reported")):
                poll_state["recoverable_failure_reported"] = True
                events.append(
                    adapter._stage_event(
                        run_id,
                        "stage_update",
                        (
                            "OpenClaw HTML slide generation reported a recoverable "
                            "subtask failure; continuing to watch for PPTX or HTML "
                            "fallback artifacts."
                        ),
                        min(88, int(poll_state.get("progress", 20)) + 4),
                    )
                )
        else:
            raise RuntimeError(
                "OpenClaw task family failed before producing a final artifact: "
                f"{failed_task_label}"
            )

    progress = int(poll_state.get("progress", 20))
    last_artifact_count = int(poll_state.get("last_artifact_count", 0))
    if len(adapter.last_artifact_paths) > last_artifact_count:
        poll_state["last_artifact_count"] = len(adapter.last_artifact_paths)
        debug_count = sum(
            1 for path in adapter.last_artifact_paths if Path(path).suffix.lower() == ".json"
        )
        primary_paths = adapter._primary_output_artifact_paths(artifact_filter_key)
        progress = 90 if primary_paths else min(88, progress + 6)
        poll_state["progress"] = progress
        if primary_paths:
            for artifact in adapter.last_artifacts:
                artifact.run_id = artifact.run_id or run_id
            events.append(
                AgentRunEvent(
                    run_id=run_id,
                    event_type="artifact_found",
                    status="running",
                    progress=90,
                    payload={
                        "protocol": "openclaw.cli.v1",
                        "mode": adapter.mode,
                        "artifact_paths": list(adapter.last_artifact_paths),
                        "artifacts": [
                            artifact_to_payload(item) for item in adapter.last_artifacts
                        ],
                        "reportDirs": sorted(report_dirs),
                        "taskFamily": adapter._task_family_summary(matching_tasks),
                    },
                    step=AgentRunStep(
                        id=f"{run_id}_openclaw_artifact_found",
                        label=f"OpenClaw final artifact found: {primary_paths[-1]}",
                        status="completed",
                        timestamp=now_iso(),
                    ),
                )
            )
        elif debug_count:
            events.append(
                adapter._stage_event(
                    run_id,
                    "stage_update",
                    (
                        f"OpenClaw has generated {debug_count} intermediate evidence "
                        "file(s); waiting for the final deliverable."
                    ),
                    progress,
                )
            )

    running_tasks = [
        task for task in matching_tasks if task.get("status") in {"queued", "running"}
    ]
    if matching_tasks:
        display_task = next(iter(running_tasks), matching_tasks[0])
        label = adapter._summarize_task_label(
            display_task,
            artifact_filter_key,
            user_content=input_data.content,
        )
    elif report_dirs:
        label = adapter._summarize_user_request_label(
            input_data.content,
            artifact_filter_key,
            suffix="正在监听报告目录和最终产物。",
        )
    else:
        label = adapter._summarize_user_request_label(
            input_data.content,
            artifact_filter_key,
            suffix="等待 OpenClaw 阶段输出或最终产物。",
        )

    now = monotonic()
    last_label = str(poll_state.get("last_label", ""))
    last_emit_at = float(poll_state.get("last_visible_emit_at", 0.0))
    should_emit_heartbeat = now - last_emit_at >= 60
    evidence_count = sum(
        1 for path in adapter.last_artifact_paths if Path(path).suffix.lower() == ".json"
    )
    should_emit_evidence_heartbeat = should_emit_heartbeat and evidence_count > 0
    if label != last_label or should_emit_heartbeat:
        poll_state["last_label"] = label
        poll_state["last_visible_emit_at"] = now
        progress = min(85, int(poll_state.get("progress", 20)) + 8)
        poll_state["progress"] = progress
        if should_emit_evidence_heartbeat and label == last_label:
            label = (
                f"{label} Found {evidence_count} intermediate evidence file(s); "
                "still waiting for the final deliverable."
            )
        elif should_emit_heartbeat and label == last_label:
            running_count = len(running_tasks)
            label = (
                f"{label} 已跟踪 {running_count or len(matching_tasks) or 1} "
                "个后台任务。"
            )
        events.append(adapter._stage_event(run_id, "stage_update", label, progress))

    adapter.last_diagnostics.update(
        {
            "reportDirs": sorted(report_dirs),
            "matchingTaskCount": len(matching_tasks),
            "runningTaskCount": len(running_tasks),
            "artifactPaths": list(adapter.last_artifact_paths),
            "artifactCount": len(adapter.last_artifact_paths),
            "lastStage": label,
        }
    )
    return events
