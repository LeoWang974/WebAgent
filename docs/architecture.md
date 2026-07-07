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

