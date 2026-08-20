# File purpose: Verifies run-scoped file stability detection and terminal watcher states.
# Main declarations: tests cover pending, staging, ready, disappeared, and timeout transitions.

import asyncio
import zipfile

import pytest

from app.services.run_artifact_watcher import RunArtifactWatcher


@pytest.mark.asyncio
async def test_watcher_emits_pending_staging_then_ready(tmp_path):
    watcher = RunArtifactWatcher(
        tmp_path,
        poll_interval_seconds=0.01,
        stable_seconds=0.02,
        stable_samples=2,
    )
    output = tmp_path / "report.md"
    output.write_text("draft", encoding="utf-8")

    assert [item.status for item in watcher.poll()] == ["pending"]
    output.write_text("final report", encoding="utf-8")
    assert [item.status for item in watcher.poll()] == ["staging"]
    await asyncio.sleep(0.03)
    transitions = watcher.poll()

    assert [item.status for item in transitions] == ["ready"]
    assert transitions[0].size_bytes == output.stat().st_size
    assert transitions[0].stable_at is not None


@pytest.mark.asyncio
async def test_watcher_marks_disappeared_file_failed(tmp_path):
    watcher = RunArtifactWatcher(tmp_path, stable_seconds=10)
    output = tmp_path / "deck.pptx"
    output.write_bytes(b"partial")
    watcher.poll()
    output.unlink()

    transitions = watcher.poll()

    assert [item.status for item in transitions] == ["failed"]
    assert "disappeared" in str(transitions[0].error)


@pytest.mark.asyncio
async def test_watcher_settle_fails_unstable_file(tmp_path):
    watcher = RunArtifactWatcher(
        tmp_path,
        poll_interval_seconds=0.01,
        stable_seconds=10,
    )
    output = tmp_path / "page.html"
    output.write_text("<html>", encoding="utf-8")
    watcher.poll()

    transitions = await watcher.settle(0.02)

    assert transitions[-1].status == "failed"
    assert "staging timeout" in str(transitions[-1].error)


@pytest.mark.asyncio
async def test_watcher_rejects_incomplete_office_container(tmp_path):
    watcher = RunArtifactWatcher(
        tmp_path,
        poll_interval_seconds=0.01,
        stable_seconds=0.01,
        stable_samples=2,
    )
    output = tmp_path / "deck.pptx"
    output.write_bytes(b"not-a-zip")

    assert [item.status for item in watcher.poll()] == ["pending"]
    await asyncio.sleep(0.02)
    assert [item.status for item in watcher.poll()] == ["staging"]
    transitions = await watcher.settle(0.02)

    assert transitions[-1].status == "failed"
    assert "ZIP container" in str(transitions[-1].error)


@pytest.mark.asyncio
async def test_watcher_accepts_complete_office_container_and_ignores_context(tmp_path):
    watcher = RunArtifactWatcher(
        tmp_path,
        poll_interval_seconds=0.01,
        stable_seconds=0.01,
        stable_samples=2,
    )
    context_file = tmp_path / "context" / "input.md"
    context_file.parent.mkdir()
    context_file.write_text("input", encoding="utf-8")
    output = tmp_path / "artifacts" / "deck.pptx"
    output.parent.mkdir()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")

    assert [item.status for item in watcher.poll()] == ["pending"]
    await asyncio.sleep(0.02)
    transitions = watcher.poll()

    assert [item.status for item in transitions] == ["ready"]
    assert transitions[0].path == output.resolve()


@pytest.mark.asyncio
async def test_watcher_ignores_dependency_and_cache_directories(tmp_path):
    watcher = RunArtifactWatcher(tmp_path)
    for relative_path in (
        "node_modules/package/readme.md",
        ".git/hooks/example.json",
        "__pycache__/debug.json",
        ".next-build/cache/page.html",
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not an artifact", encoding="utf-8")

    assert watcher.poll() == []
