# Artifact Manifest Protocol v2

WebAgent uses `webagent.artifacts.v2` as the canonical contract between an Agent adapter and the
artifact persistence pipeline. User prompts remain unchanged; the adapter owns this protocol.

## Location and lifecycle

Each Agent Run writes `artifact-manifest.json` inside its managed artifact directory. The file is
updated atomically while the run is active and copied into the durable artifact storage directory
before database records are created.

Manifest status transitions are:

```text
collecting -> finalized
           -> failed
```

An Agent Run cannot complete from a `collecting` or `failed` manifest. A manifest containing a
`missing` entry also blocks successful completion.

## Schema

```json
{
  "schema": "webagent.artifacts.v2",
  "run_id": "run-id",
  "conversation_id": "conversation-id",
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
      "discovered_by": "terminal_output",
      "source_dir": "/managed/run/artifacts",
      "size_bytes": 1024,
      "sha256": "64-lowercase-hex-characters"
    }
  ]
}
```

## Discovery sources

- `adapter_event`: the Agent or tool layer explicitly declared the output.
- `terminal_output`: the adapter extracted an explicit path from Agent output.
- `recovery_scan`: a bounded run-directory scan recovered the file.

`recovery_scan` is diagnostic fallback, not the primary contract. Its use is recorded through
`recovery_used` so reliability can be measured.

## Integrity and identity

Before ingestion, WebAgent verifies each ready entry's file size and SHA-256. The manifest entry is
the run-scoped identity; content hashes may deduplicate physical blobs but must never suppress the
artifact association for a new run.

## Completion rules

WebAgent may mark an Agent Run completed only after:

1. The manifest belongs to the current `run_id`.
2. The manifest status is `finalized`.
3. Every entry is `ready` and passes size/checksum verification.
4. The durable manifest and artifact files have been written.
5. Database artifact records and `artifact_created` events have been committed.

Legacy adapters without a v2 manifest continue through the old discovery path temporarily. That
path is marked `legacy_fallback` in run diagnostics and should be removed after all adapters emit
v2 manifests.
