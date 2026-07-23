# OpenClaw Event Protocol

This document defines the event contract that WebAgent expects OpenClaw CLI/Gateway
to expose for long-running agent tasks.

The goal is to stop relying on terminal text parsing and directory scanning as the
primary integration path. OpenClaw should explicitly report progress, tool stages,
artifacts, completion, and failures in a stable JSON shape.

## Protocol Version

Current protocol:

```text
openclaw.event.v1
```

Every protocol event should include:

```json
{
  "protocol": "openclaw.event.v1",
  "event_type": "stage_update",
  "label": "正在检索行业资料",
  "progress": 35,
  "status": "running"
}
```

## Where Events Should Appear

WebAgent currently reads OpenClaw progress from:

```bash
openclaw tasks list --json
```

The preferred response shape is:

```json
{
  "tasks": [
    {
      "taskId": "task-main",
      "status": "running",
      "task": "webagent_skill=deep_research\nwebagent_run_id=run_123",
      "events": [
        {
          "protocol": "openclaw.event.v1",
          "event_type": "stage_started",
          "label": "开始深度研究流程",
          "progress": 10,
          "status": "completed"
        }
      ]
    }
  ]
}
```

WebAgent will recursively scan each task object for protocol events, so `events`
can be nested as long as each event preserves the fields below.

## Required Fields

`protocol`
: Must be `openclaw.event.v1`.

`event_type`
: One of `stage_started`, `stage_update`, `tool_call`, `artifact_found`,
`completed`, `failed`, or `cancelled`.

`label`
: User-visible progress text. It should describe the actual current work, not just
the internal task status.

`progress`
: Integer from 0 to 100.

`status`
: One of `queued`, `running`, `completed`, `failed`, or `cancelled`.

## Artifact Fields

For `artifact_found` events, OpenClaw should include:

```json
{
  "protocol": "openclaw.event.v1",
  "event_type": "artifact_found",
  "label": "中文 Markdown 报告已生成",
  "progress": 90,
  "status": "completed",
  "artifact_paths": [
    "/home/user/.openclaw/workspace/reports/topic/report.md"
  ],
  "artifact_type": "markdown_report",
  "source_dir": "/home/user/.openclaw/workspace/reports/topic",
  "title": "主题研究报告"
}
```

Supported `artifact_type` values:

```text
markdown_report
html_page
ppt_deck
image_result
data_table
json_debug
unknown
```

`artifact_paths` should contain final user-facing deliverables first. Intermediate
JSON/debug files may be reported as `json_debug`; WebAgent will decide whether to
show them based on developer mode.

## Recommended Event Flow

For deep research:

```json
[
  {
    "protocol": "openclaw.event.v1",
    "event_type": "stage_started",
    "label": "开始深度研究流程",
    "progress": 10,
    "status": "completed"
  },
  {
    "protocol": "openclaw.event.v1",
    "event_type": "tool_call",
    "label": "正在检索主题乐园行业数据与案例",
    "progress": 30,
    "status": "running"
  },
  {
    "protocol": "openclaw.event.v1",
    "event_type": "stage_update",
    "label": "正在汇总 Disney、Universal、方特和长隆的商业模式",
    "progress": 60,
    "status": "running"
  },
  {
    "protocol": "openclaw.event.v1",
    "event_type": "artifact_found",
    "label": "Markdown 报告已生成",
    "progress": 90,
    "status": "completed",
    "artifact_paths": ["/home/user/.openclaw/workspace/reports/topic/report.md"],
    "artifact_type": "markdown_report",
    "source_dir": "/home/user/.openclaw/workspace/reports/topic",
    "title": "全球主题乐园竞争格局报告"
  },
  {
    "protocol": "openclaw.event.v1",
    "event_type": "completed",
    "label": "任务完成",
    "progress": 100,
    "status": "completed"
  }
]
```

For PPT generation:

```json
{
  "protocol": "openclaw.event.v1",
  "event_type": "artifact_found",
  "label": "PPTX 文件已生成",
  "progress": 90,
  "status": "completed",
  "artifact_paths": [
    "/home/user/.openclaw/workspace/ppt_decks/topic/topic.pptx"
  ],
  "artifact_type": "ppt_deck",
  "source_dir": "/home/user/.openclaw/workspace/ppt_decks/topic",
  "title": "主题演示文稿"
}
```

If an HTML fallback is also generated, it can be included after the PPTX:

```json
{
  "artifact_paths": [
    "/home/user/.openclaw/workspace/ppt_decks/topic/topic.pptx",
    "/home/user/.openclaw/workspace/ppt_decks/topic/index.html"
  ],
  "artifact_type": "ppt_deck"
}
```

## Failure Diagnostics

When a task fails, OpenClaw should emit:

```json
{
  "protocol": "openclaw.event.v1",
  "event_type": "failed",
  "label": "PPTX 导出失败：HTML 已生成，但转换器返回错误",
  "progress": 72,
  "status": "failed",
  "exit_code": 1,
  "stderr_tail": "last 20 lines of stderr",
  "last_stage": "正在导出 PPTX 文件",
  "source_dir": "/home/user/.openclaw/workspace/ppt_decks/topic",
  "artifact_paths": [
    "/home/user/.openclaw/workspace/ppt_decks/topic/index.html"
  ],
  "artifact_type": "html_page"
}
```

Recommended diagnostic fields:

`exit_code`
: Process exit code when available.

`stderr_tail`
: Short stderr tail, preferably capped to 20-50 lines.

`last_stage`
: Last meaningful user-visible stage.

`source_dir`
: Directory where partial artifacts may exist.

`artifact_paths`
: Any partial or fallback artifacts that were successfully produced.

## WebAgent Consumption

Current WebAgent integration points:

- `services/agent-runtime/agent_runtime/adapters/openclaw_utils.py`
  - `OPENCLAW_EVENT_PROTOCOL`
  - `extract_protocol_events()`
- `services/agent-runtime/agent_runtime/adapters/openclaw_adapter.py`
  - `_protocol_events_from_tasks()`
  - `_remember_structured_artifacts_from_value()`
  - `_poll_task_family_snapshot()`

WebAgent behavior:

- Converts each protocol event into an `AgentRunEvent`.
- Displays `label` in the chat progress bubbles.
- Uses `progress` for run progress.
- Records `artifact_found` paths as artifacts.
- Keeps directory scanning as a compatibility fallback for older OpenClaw versions.

## Migration Requirement

This protocol only works on a server if the deployed OpenClaw CLI/Gateway includes
the event-recording changes.

Do not rely on local manual edits to an installed package. For production or server
migration, use one of these approaches:

1. Fork OpenClaw and deploy a pinned branch or commit.
2. Upstream the protocol implementation to OpenClaw.
3. Package OpenClaw with this protocol support as an internal dependency.

Example pinned install:

```bash
pip install "git+https://github.com/your-org/openclaw.git@webagent-protocol-v1"
```

WebAgent should continue to keep fallback parsing, but the server checkpoint should
use a protocol-capable OpenClaw build for reliable long-task progress and artifact
delivery.
