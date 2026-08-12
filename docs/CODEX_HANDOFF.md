# Codex Handoff Archive

This file is kept only as a historical placeholder for early MVP handoff notes.

The previous content described an obsolete mock-store phase and contained mojibake text. It has been replaced to avoid misleading future development work.

Current source of truth:

- `README.md`: project overview, local startup, CCI bare-metal startup.
- `docs/TESTING.md`: backend and frontend verification commands.
- `docs/CCI_BARE_METAL.md`: CCI non-Docker runtime notes.
- WebAgent now uses Hermes as its only runtime adapter.
- `services/api/README.md`: backend service scope and startup.

Current backend storage state:

- `app.services.mock_store` has been removed.
- Auth, sessions, messages, files, artifacts, settings, models, skills, folders, admin users, Agent Runs, and Agent Run Events are database-backed.
- Agent execution should go through queued Agent Runs and runtime adapters.
