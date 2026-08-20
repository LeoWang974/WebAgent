# Artifact Manifest Protocol v3

WebAgent uses `webagent.artifacts.v3` as the canonical contract between an Agent adapter and the
artifact persistence pipeline. User prompts remain unchanged; the adapter owns this protocol.

## Location and lifecycle

Each Agent Run writes `artifact-manifest.json` inside its managed artifact directory. The file is
updated atomically while the run is active and copied into the durable artifact storage directory
before database records are created.

The run manifest transitions are:

```text
collecting -> finalized
           -> failed
```

Each file has its own stability state machine:

```text
pending -> staging -> ready
                   -> failed
```

The run-scoped watcher observes size and mtime changes. A file becomes `ready` only after the
configured stable time window and sample count. `pending` or `staging` entries are converted to
`failed` when the run finalizes; they are never ingested as complete artifacts.

## Schema

```json
{
  "schema": "webagent.artifacts.v3",
  "run_id": "run-id",
  "conversation_id": "conversation-id",
  "workspace_dir": "/managed/run",
  "artifacts_dir": "/managed/run/artifacts",
  "producer": "hermes_cli_adapter",
  "status": "finalized",
  "created_at": "2026-08-19T10:00:00Z",
  "updated_at": "2026-08-19T10:01:00Z",
  "finalized_at": "2026-08-19T10:01:00Z",
  "recovery_used": false,
  "errors": [],
  "artifacts": [
    {
      "entry_id": "stable-path-identity",
      "path": "/managed/run/artifacts/report.md",
      "artifact_type": "markdown_report",
      "title": "report",
      "role": "primary",
      "status": "ready",
      "discovered_by": "file_watcher",
      "source_dir": "/managed/run/artifacts",
      "path_scope": "managed",
      "size_bytes": 1024,
      "mtime_ns": 1787114460000000000,
      "first_seen_at": "2026-08-19T10:00:30Z",
      "stable_at": "2026-08-19T10:00:32Z",
      "error": null,
      "sha256": "64-lowercase-hex-characters"
    }
  ]
}
```

## Discovery sources

- `adapter_event`: the Agent or tool layer explicitly declared the output.
- `file_watcher`: the run-scoped watcher observed and stabilized the file.
- `terminal_output`: the adapter extracted an explicit path from Agent output.
- `recovery_scan`: a bounded run-directory scan recovered the file.

`recovery_scan` is diagnostic fallback, not the primary contract. Its use is recorded through
`recovery_used` so reliability can be measured.

## Integrity and identity

Before ingestion, WebAgent verifies each ready entry's file size and SHA-256. The manifest entry is
the run-scoped identity; content hashes may deduplicate physical blobs but must never suppress the
artifact association for a new run.

Each persisted artifact is linked to its Agent Run through `run_artifacts`. Historical path or
content-hash matches are not used to discard a new Run's output. The legacy `artifacts.run_id`
column remains populated for API compatibility, while `run_artifacts` is the durable ownership
record and is backfilled for existing data by Alembic migration `20260819_0012`.

## Completion rules

WebAgent may mark an Agent Run completed only after:

1. The manifest belongs to the current `run_id`.
2. The manifest status is `finalized`.
3. No entry remains `pending` or `staging`.
4. Every `ready` entry passes size/checksum verification; `failed` entries remain diagnostic.
5. The durable manifest and artifact files have been written.
6. Database artifact records and `run_artifacts` ownership rows have been committed.

SSE `artifact_state` and `artifact_created` events are immediate notifications only. After a run
reaches a terminal state, the web client queries `/api/artifacts?sessionId=...&runId=...` and treats
that response as the authoritative artifact list.

## Run isolation

The watcher scans only the current run workspace:
`<workspace-root>/<user-id>/<conversation-id>/<run-id>`. Files that existed when the watcher was
created are baseline inputs and are ignored unless Hermes later modifies or explicitly reports
them. Durable storage remains separated by user, conversation, and run.

Legacy v2 manifests remain readable. Runs without a manifest continue through the old discovery
path temporarily. That
path is marked `legacy_fallback` in run diagnostics and should be removed after all adapters emit
v3 manifests.
