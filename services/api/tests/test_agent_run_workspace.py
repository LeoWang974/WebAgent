import json

from app.core.config import settings
from app.services.agent_run_workspace import run_workspace_dir


def test_run_workspace_is_an_isolated_npm_project(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "agent_run_workspace_root", str(tmp_path))

    workspace = run_workspace_dir("run-one", "conversation-one", "user-one")

    package = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
    assert package == {
        "name": "webagent-run-run-one",
        "private": True,
        "version": "0.0.0",
    }
