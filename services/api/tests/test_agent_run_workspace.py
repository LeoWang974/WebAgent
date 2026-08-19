# File purpose: Verifies test agent run workspace behavior and its regression contracts.
# Main declarations: test_run_workspace_is_an_isolated_npm_project verifies run workspace is an
# isolated npm project.

import json

from app.core.config import settings
from app.services.agent_run_workspace import _stage_artifact_file, run_workspace_dir


def test_run_workspace_is_an_isolated_npm_project(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "agent_run_workspace_root", str(tmp_path))

    workspace = run_workspace_dir("run-one", "conversation-one", "user-one")

    package = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
    assert package == {
        "name": "webagent-run-run-one",
        "private": True,
        "version": "0.0.0",
    }


def test_stage_artifact_file_is_idempotent_when_destination_exists(tmp_path):
    source = tmp_path / "source.html"
    destination = tmp_path / "context.html"
    source.write_text("new source", encoding="utf-8")
    destination.write_text("existing staged artifact", encoding="utf-8")

    _stage_artifact_file(source, destination)

    assert destination.read_text(encoding="utf-8") == "existing staged artifact"
