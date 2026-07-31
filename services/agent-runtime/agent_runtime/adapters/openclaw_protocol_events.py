from time import monotonic
from collections.abc import Callable

from ..schemas import AgentArtifactRef, AgentRunEvent, AgentRunStep
from .openclaw_utils import (
    OPENCLAW_EVENT_PROTOCOL,
    artifact_to_payload,
    extract_protocol_events,
    now_iso,
)


def protocol_events_from_tasks(
    run_id: str,
    tasks: list[dict[str, object]],
    poll_state: dict[str, object],
    *,
    compact_label: Callable[[str], str],
    remember_artifact_ref: Callable[[AgentArtifactRef], None],
) -> list[AgentRunEvent]:
    emitted_keys = poll_state.setdefault("emitted_protocol_event_keys", set())
    if not isinstance(emitted_keys, set):
        emitted_keys = set()
        poll_state["emitted_protocol_event_keys"] = emitted_keys

    events: list[AgentRunEvent] = []
    for task in tasks:
        for event in extract_protocol_events(task):
            raw_artifacts = event.get("artifacts")
            artifacts = [
                artifact
                for artifact in raw_artifacts or []
                if isinstance(artifact, AgentArtifactRef)
            ]
            for artifact in artifacts:
                artifact.run_id = artifact.run_id or run_id
                remember_artifact_ref(artifact)

            event_type = str(event.get("event_type") or "stage_update")
            label = compact_label(str(event.get("label") or ""))
            if not label and event_type == "artifact_found":
                label = "OpenClaw reported a generated artifact."
            if not label:
                continue

            source = event.get("source") if isinstance(event.get("source"), dict) else {}
            progress = event.get("progress")
            progress_value = (
                int(progress)
                if isinstance(progress, int)
                else min(88, int(poll_state.get("progress", 20)) + 6)
            )
            status = str(event.get("status") or "running").lower()
            step_status = "completed" if status in {"completed", "succeeded"} else "running"
            if status in {"failed", "timed_out", "cancelled"}:
                step_status = "failed"

            artifact_paths = [artifact.path for artifact in artifacts]
            event_key = "|".join(
                [
                    str(source.get("taskId") or source.get("runId") or ""),
                    event_type,
                    label,
                    ",".join(artifact_paths),
                ]
            )
            if event_key in emitted_keys:
                continue
            emitted_keys.add(event_key)
            poll_state["progress"] = max(int(poll_state.get("progress", 20)), progress_value)
            poll_state["last_label"] = label
            poll_state["last_visible_emit_at"] = monotonic()

            events.append(
                AgentRunEvent(
                    run_id=run_id,
                    event_type=event_type,
                    status="running" if step_status != "failed" else "failed",
                    progress=progress_value,
                    payload={
                        "protocol": OPENCLAW_EVENT_PROTOCOL,
                        "source": source,
                        "artifacts": [artifact_to_payload(artifact) for artifact in artifacts],
                        "rawOpenClawEvent": event.get("raw"),
                    },
                    step=AgentRunStep(
                        id=f"{run_id}_openclaw_protocol_{len(emitted_keys)}",
                        label=label,
                        status=step_status,
                        timestamp=now_iso(),
                    ),
                )
            )
    return events
