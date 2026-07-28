import json
import re
from datetime import UTC, datetime
from pathlib import Path

from ..schemas import AgentArtifactRef

OPENCLAW_EVENT_PROTOCOL = "openclaw.event.v1"

OPENCLAW_SKILL_MAPPING = {
    "data_analysis": {
        "name": "OpenClaw data analysis",
        "capability": "data_analysis",
        "instruction": (
            "Run OpenClaw's data analysis workflow. Prefer attached or referenced CSV/XLSX/table "
            "artifacts, inspect the data, summarize findings, and create a concise report or table."
        ),
        "artifact_type_hint": "data_table or markdown_report",
    },
    "deep_research": {
        "name": "OpenClaw research",
        "capability": "research",
        "instruction": (
            "Run OpenClaw's research workflow. Search and synthesize evidence, "
            "keep citations clear, "
            "and produce one final report instead of scattering the answer across sub-reports."
        ),
        "artifact_type_hint": "markdown_report or html_page",
    },
    "ppt_generation": {
        "name": "OpenClaw presentation generation",
        "capability": "presentation",
        "instruction": (
            "Run OpenClaw's presentation generation workflow. Prefer the sn-ppt-workbench skill "
            "when it is available. Use the most relevant source report or HTML content, generate "
            "slide pages, and export a PPTX deliverable when possible."
        ),
        "artifact_type_hint": "ppt_deck and optional html_page fallback",
    },
    "html_generation": {
        "name": "OpenClaw HTML report generation",
        "capability": "html_report_generation",
        "instruction": (
            "Run OpenClaw's report-html-v2 workflow. Use the most relevant source Markdown "
            "report path from the WebAgent runtime context, generate a standalone HTML report, "
            "and do not redo research unless the source report is missing."
        ),
        "artifact_type_hint": "html_page",
    },
    "u1_image": {
        "name": "OpenClaw image generation",
        "capability": "image_generation",
        "instruction": (
            "Run OpenClaw's image generation workflow. Treat U1 as the image "
            "generation capability, "
            "not as a reference image name. Generate image files matching the user's request."
        ),
        "artifact_type_hint": "image_result",
    },
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def clean_text_output(text: str) -> str:
    lines = []
    ansi_pattern = re.compile(r"\x1b\[[0-9;]*m")
    for line in text.splitlines():
        cleaned = ansi_pattern.sub("", line).strip()
        if not cleaned:
            continue
        if cleaned.startswith("[skills]"):
            continue
        lines.append(cleaned)
    return "\n".join(lines).strip()


def extract_json_output(text: str) -> str | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None

    result = parsed.get("result")
    if isinstance(result, dict):
        result_output = extract_json_output(json.dumps(result, ensure_ascii=False))
        if result_output:
            return result_output

    for key in ("output", "reply", "message", "content", "text"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    payloads = parsed.get("payloads")
    if isinstance(payloads, list):
        parts = []
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            text_value = payload.get("text")
            if isinstance(text_value, str) and text_value.strip():
                parts.append(text_value.strip())
        if parts:
            return "\n".join(parts)

    return json.dumps(parsed, ensure_ascii=False)


def extract_output(stdout: str, stderr: str) -> str:
    for data in (stdout, stderr):
        cleaned = clean_text_output(data)
        if not cleaned:
            continue
        parsed_output = extract_json_output(cleaned)
        if parsed_output:
            return parsed_output
        return cleaned
    return ""


def extract_paths(text: str) -> list[str]:
    pattern = re.compile(
        r"(?P<path>(?:[A-Za-z]:\\|/mnt/[a-z]/|/)[^\s'\"<>]+"
        r"\.(?:md|markdown|html|htm|pptx|ppt|png|jpg|jpeg|webp|csv|xlsx|json))",
        re.IGNORECASE,
    )
    return [match.group("path").rstrip(".,;:") for match in pattern.finditer(text)]


def guess_artifact_type(path: str) -> str | None:
    suffix = Path(path).suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown_report"
    if suffix in {".html", ".htm"}:
        return "html_page"
    if suffix in {".ppt", ".pptx"}:
        return "ppt_deck"
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return "image_result"
    if suffix in {".csv", ".xlsx"}:
        return "data_table"
    if suffix == ".json":
        return "debug_json"
    return None


def source_dir_from_path(path: str) -> str | None:
    return str(Path(path).parent)


def title_from_path(path: str) -> str:
    return Path(path).stem


def safe_file_stem(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "-", value.strip()).strip("-")
    return cleaned[:80] or "openclaw-report"


def is_openclaw_bootstrap_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    bootstrap_names = {
        "AGENTS.md",
        "SOUL.md",
        "TOOLS.md",
        "IDENTITY.md",
        "USER.md",
        "HEARTBEAT.md",
        "BOOTSTRAP.md",
    }
    if "/.openclaw/workspace/" not in normalized:
        return False
    return normalized.rsplit("/", 1)[-1] in bootstrap_names


def string_value(value: dict, *keys: str) -> str | None:
    for key in keys:
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


def extract_paths_from_value(value: object) -> list[str]:
    if isinstance(value, str):
        return extract_paths(value)
    if isinstance(value, list):
        paths: list[str] = []
        for item in value:
            paths.extend(extract_paths_from_value(item))
        return paths
    if isinstance(value, dict):
        paths: list[str] = []
        for item in value.values():
            paths.extend(extract_paths_from_value(item))
        return paths
    return []


def artifact_paths_from_mapping(value: dict) -> list[str]:
    paths: list[str] = []
    for key, item in value.items():
        normalized_key = key.lower()
        if normalized_key in {
            "artifact_path",
            "artifact_paths",
            "artifactpath",
            "path",
            "paths",
            "filepath",
            "file_path",
            "mediaurl",
            "media_url",
        }:
            paths.extend(extract_paths_from_value(item))
    return paths


def collect_artifact_refs(
    value: object,
    artifacts: list[AgentArtifactRef],
    seen: set[str],
    inherited: dict[str, str | None] | None = None,
) -> None:
    inherited = inherited or {}
    if isinstance(value, dict):
        artifact_type = string_value(
            value,
            "artifact_type",
            "artifactType",
            "type",
        ) or inherited.get("artifact_type")
        source_dir = string_value(
            value,
            "source_dir",
            "sourceDir",
        ) or inherited.get("source_dir")
        run_id = string_value(value, "run_id", "runId") or inherited.get("run_id")
        title = string_value(value, "title", "name") or inherited.get("title")
        context = {
            "artifact_type": artifact_type,
            "source_dir": source_dir,
            "run_id": run_id,
            "title": title,
        }

        direct_paths = artifact_paths_from_mapping(value)
        for path in direct_paths:
            if path in seen:
                continue
            seen.add(path)
            artifacts.append(
                AgentArtifactRef(
                    path=path,
                    artifact_type=artifact_type,
                    run_id=run_id,
                    source_dir=source_dir,
                    title=title,
                )
            )

        for item in value.values():
            collect_artifact_refs(item, artifacts, seen, context)
    elif isinstance(value, list):
        for item in value:
            collect_artifact_refs(item, artifacts, seen, inherited)


def extract_structured_artifacts(stdout: str, stderr: str) -> list[AgentArtifactRef]:
    artifacts: list[AgentArtifactRef] = []
    seen: set[str] = set()
    for text in (stdout, stderr):
        cleaned = clean_text_output(text)
        if not cleaned:
            continue
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            continue
        collect_artifact_refs(parsed, artifacts, seen)
    return artifacts


def extract_structured_artifact_paths(stdout: str, stderr: str) -> list[str]:
    return [artifact.path for artifact in extract_structured_artifacts(stdout, stderr)]


def artifact_to_payload(artifact: AgentArtifactRef) -> dict[str, object]:
    return {
        "artifact_paths": [artifact.path],
        "artifact_path": artifact.path,
        "artifact_type": artifact.artifact_type,
        "run_id": artifact.run_id,
        "source_dir": artifact.source_dir,
        "title": artifact.title,
    }


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _event_type(value: dict) -> str | None:
    raw = string_value(
        value,
        "event_type",
        "eventType",
        "openclaw_event",
        "openclawEvent",
        "type",
    )
    if not raw:
        return None
    normalized = raw.strip().lower().replace("-", "_").replace(".", "_")
    aliases = {
        "artifact": "artifact_found",
        "artifact_created": "artifact_found",
        "artifact_found": "artifact_found",
        "complete": "completed",
        "completed": "completed",
        "done": "completed",
        "failed": "failed",
        "failure": "failed",
        "stage": "stage_update",
        "stage_started": "stage_started",
        "stage_update": "stage_update",
        "tool": "tool_call",
        "tool_call": "tool_call",
    }
    return aliases.get(normalized, normalized)


def _explicit_event_type(value: dict) -> str | None:
    raw = string_value(
        value,
        "event_type",
        "eventType",
        "openclaw_event",
        "openclawEvent",
    )
    if not raw:
        return None
    return _event_type({"event_type": raw})


def _event_label(value: dict) -> str | None:
    return string_value(
        value,
        "label",
        "message",
        "progressSummary",
        "progress_summary",
        "summary",
        "text",
        "content",
    )


def _looks_like_protocol_event(value: dict) -> bool:
    protocol = string_value(value, "protocol")
    if protocol and protocol.startswith("openclaw."):
        return True
    if _explicit_event_type(value) and (
        _event_label(value)
        or _int_value(value.get("progress")) is not None
        or artifact_paths_from_mapping(value)
    ):
        return True
    return False


def collect_protocol_events(
    value: object,
    events: list[dict[str, object]],
    inherited: dict[str, object] | None = None,
) -> None:
    inherited = inherited or {}
    if isinstance(value, dict):
        context = {
            **inherited,
            **{
                key: value.get(key)
                for key in (
                    "taskId",
                    "runId",
                    "sourceId",
                    "parentFlowId",
                    "runtime",
                    "status",
                )
                if value.get(key) is not None
            },
        }
        if _looks_like_protocol_event(value):
            artifacts: list[AgentArtifactRef] = []
            collect_artifact_refs(value, artifacts, set())
            event_type = _event_type(value) or (
                "artifact_found" if artifacts else "stage_update"
            )
            events.append(
                {
                    "event_type": event_type,
                    "label": _event_label(value),
                    "status": string_value(value, "status") or context.get("status"),
                    "progress": _int_value(value.get("progress")),
                    "artifacts": artifacts,
                    "source": context,
                    "raw": value,
                }
            )
        for item in value.values():
            collect_protocol_events(item, events, context)
    elif isinstance(value, list):
        for item in value:
            collect_protocol_events(item, events, inherited)


def extract_protocol_events(value: object) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    collect_protocol_events(value, events)
    return events
