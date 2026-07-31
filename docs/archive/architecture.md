# Architecture

Planned architecture:

```text
apps/web
  -> services/api
    -> services/agent-runtime
      -> openclaw or hermes
    -> services/renderer
    -> PostgreSQL / Redis / object storage
```

The frontend should not directly depend on openclaw or hermes. Agent runtimes are accessed through backend adapters.
# Archived

This early design note is kept for historical context. Current implementation
and deployment notes live in `README.md`, `docs/CCI_BARE_METAL.md`,
`docs/PRODUCTION.md`, and `docs/TESTING.md`.

