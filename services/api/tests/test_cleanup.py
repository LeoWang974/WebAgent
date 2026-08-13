import os
import time
from pathlib import Path

from app.services.cleanup import cleanup_expired_runtime_files


def test_cleanup_expired_runtime_files_keeps_recent_files(tmp_path: Path):
    prompt_dir = tmp_path / "runtime" / "hermes-prompts"
    run_dir = tmp_path / "runtime" / "hermes-runs"
    prompt_dir.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    old_prompt = prompt_dir / "old.txt"
    recent_prompt = prompt_dir / "recent.txt"
    old_run = run_dir / "old-run"
    old_run.mkdir()
    old_prompt.write_text("old", encoding="utf-8")
    recent_prompt.write_text("recent", encoding="utf-8")
    (old_run / "artifact.md").write_text("old", encoding="utf-8")

    old_timestamp = time.time() - 10 * 24 * 60 * 60
    os.utime(old_prompt, (old_timestamp, old_timestamp))
    os.utime(old_run, (old_timestamp, old_timestamp))

    deleted = cleanup_expired_runtime_files(max_age_days=7, repo_root=tmp_path)

    assert deleted == 2
    assert not old_prompt.exists()
    assert not old_run.exists()
    assert recent_prompt.exists()


def test_cleanup_expired_runtime_files_removes_run_homes_and_raw_logs(tmp_path: Path):
    user_runs = tmp_path / "runtime" / "users" / "user-1" / "conversations" / "chat-1" / "runs"
    old_runtime = user_runs / "old-run"
    recent_runtime = user_runs / "recent-run"
    old_runtime.mkdir(parents=True)
    recent_runtime.mkdir()
    (old_runtime / "hermes-home").mkdir()

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    old_log = logs_dir / "hermes-raw-old.log"
    recent_log = logs_dir / "hermes-raw-recent.log"
    unrelated_log = logs_dir / "api.log"
    for path in (old_log, recent_log, unrelated_log):
        path.write_text("log", encoding="utf-8")

    old_timestamp = time.time() - 10 * 24 * 60 * 60
    os.utime(old_runtime, (old_timestamp, old_timestamp))
    os.utime(old_log, (old_timestamp, old_timestamp))
    os.utime(unrelated_log, (old_timestamp, old_timestamp))

    deleted = cleanup_expired_runtime_files(max_age_days=7, repo_root=tmp_path)

    assert deleted == 2
    assert not old_runtime.exists()
    assert recent_runtime.exists()
    assert not old_log.exists()
    assert recent_log.exists()
    assert unrelated_log.exists()
