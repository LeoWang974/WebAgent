from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.skills_update_scheduler import next_weekly_run_at
from app.services.skills_updater import update_sensenova_skills


def init_git_repo(path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=path, check=True, stdout=subprocess.PIPE)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        stdout=subprocess.PIPE,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path,
        check=True,
        stdout=subprocess.PIPE,
    )
    subprocess.run(["git", "add", "."], cwd=path, check=True, stdout=subprocess.PIPE)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=path,
        check=True,
        stdout=subprocess.PIPE,
    )


def test_next_weekly_run_at_schedules_friday_5pm_shanghai():
    now = datetime(2026, 7, 17, 8, 59, tzinfo=UTC)

    result = next_weekly_run_at(
        now,
        weekday=4,
        hour=17,
        minute=0,
        timezone_name="Asia/Shanghai",
    )

    assert result.isoformat() == "2026-07-17T17:00:00+08:00"


def test_next_weekly_run_at_rolls_to_next_week_after_target_time():
    now = datetime(2026, 7, 17, 9, 1, tzinfo=UTC)

    result = next_weekly_run_at(
        now,
        weekday=4,
        hour=17,
        minute=0,
        timezone_name="Asia/Shanghai",
    )

    assert result.isoformat() == "2026-07-24T17:00:00+08:00"


@pytest.mark.asyncio
async def test_update_sensenova_skills_syncs_local_repo_to_runtime_targets(tmp_path: Path):
    repo = tmp_path / "SenseNova-Skills"
    repo.mkdir()
    (repo / "sn-deep-research").mkdir()
    (repo / "sn-deep-research" / "SKILL.md").write_text("research skill", encoding="utf-8")
    init_git_repo(repo)

    cache_dir = tmp_path / "cache"
    hermes_dir = tmp_path / "hermes" / "skills"
    openclaw_dir = tmp_path / "openclaw" / "skills"

    result = await update_sensenova_skills(
        repo_url=str(repo),
        cache_dir=str(cache_dir),
        source_subdir=".",
        branch=None,
        hermes_skills_dir=str(hermes_dir),
        openclaw_skills_dir=str(openclaw_dir),
        wsl_distribution="Ubuntu",
    )

    assert result.commit
    assert result.hermes_updated is True
    assert result.openclaw_updated is True
    assert (hermes_dir / "sn-deep-research" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "research skill"
    assert (openclaw_dir / "sn-deep-research" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "research skill"
