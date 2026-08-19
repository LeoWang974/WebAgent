# File purpose: Verifies test agent runtime isolation behavior and its regression contracts.
# Main declarations: test_safe_runtime_segment_strips_path_unsafe_characters verifies safe runtime
# segment strips path unsafe characters;
# test_path_from_runtime_setting_accepts_wsl_drive_path_on_windows verifies path from runtime
# setting accepts wsl drive path on windows; _base_hermes_home handles base hermes home;
# test_build_user_runtime_context_creates_per_conversation_dirs verifies build user runtime
# context creates per conversation dirs; test_build_user_runtime_context_uses_run_model_snapshot
# verifies build user runtime context uses run model snapshot;
# test_build_user_runtime_context_resumes_latest_conversation_session verifies build user runtime
# context resumes latest conversation session; test_adapter_lock_scope_respects_configured_scope
# verifies adapter lock scope respects configured scope.

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from app.core.config import settings
from app.services.adapter_limiter import adapter_lock_scope
from app.services.model_runtime_config import ModelRuntimeConfig
from app.services.runtime_environment import (
    build_user_runtime_context,
    path_from_runtime_setting,
    safe_runtime_segment,
    scrub_runtime_credentials,
    shell_path,
)


def test_safe_runtime_segment_strips_path_unsafe_characters():
    assert safe_runtime_segment("user/with\\slashes and spaces") == "user-with-slashes and spaces"
    assert safe_runtime_segment("../") == "user"


def test_path_from_runtime_setting_accepts_wsl_drive_path_on_windows(monkeypatch):
    monkeypatch.setattr("app.services.runtime_environment.os_name", "nt")
    path = path_from_runtime_setting("/mnt/d/gitWorkSpace/WebAgent/runtime/users")
    assert str(path) == r"D:\gitWorkSpace\WebAgent\runtime\users"


def _base_hermes_home(tmp_path: Path) -> Path:
    home = tmp_path / "base-hermes"
    skills = home / "skills"
    skills.mkdir(parents=True)
    (home / ".env").write_text("SERPER_API_KEY=test\n", encoding="utf-8")
    (home / "config.yaml").write_text(
        'model:\n  provider: "custom"\n  base_url: "https://token.sensenova.cn/v1"\n',
        encoding="utf-8",
    )
    (skills / "skill.txt").write_text("hermes skill", encoding="utf-8")
    return home


def test_build_user_runtime_context_creates_per_conversation_dirs(monkeypatch, tmp_path: Path):
    runtime_root = tmp_path / "runtime-users"
    hermes_home = _base_hermes_home(tmp_path)
    monkeypatch.setattr(settings, "agent_runtime_user_root", str(runtime_root))
    monkeypatch.setattr(settings, "hermes_home", str(hermes_home))
    monkeypatch.setattr(settings, "hermes_skills_dir", "")
    monkeypatch.setattr(settings, "sensenova_api_key", "sensenova-test-key")
    monkeypatch.setattr(settings, "sensenova_base_url", "https://token.sensenova.cn/v1")

    user = SimpleNamespace(id="user/one", username="Test User")
    context = build_user_runtime_context(user, "conversation/one")

    assert context.root_dir == runtime_root / "user-one" / "conversations" / "conversation-one"
    assert context.hermes_home.exists()
    assert (context.hermes_skills_dir / "skill.txt").read_text(encoding="utf-8") == "hermes skill"
    hermes_env = (context.hermes_home / ".env").read_text(encoding="utf-8")
    assert "SERPER_API_KEY=test" in hermes_env
    assert "OPENAI_API_KEY=sensenova-test-key" in hermes_env
    assert context.adapter_lock_scope() == "conversation:user-one:conversation-one"


def test_build_user_runtime_context_uses_run_model_snapshot(monkeypatch, tmp_path: Path):
    runtime_root = tmp_path / "runtime-users"
    hermes_home = _base_hermes_home(tmp_path)
    monkeypatch.setattr(settings, "agent_runtime_user_root", str(runtime_root))
    monkeypatch.setattr(settings, "hermes_home", str(hermes_home))
    monkeypatch.setattr(settings, "hermes_skills_dir", "")

    config = ModelRuntimeConfig(
        model_config_id="model-1",
        provider="deepseek",
        model_name="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key="user-deepseek-key",
    )
    user = SimpleNamespace(id="user/one", username="Test User")
    context = build_user_runtime_context(
        user,
        "conversation/one",
        run_id="run/one",
        model_runtime_config=config,
    )

    assert context.root_dir == (
        runtime_root / "user-one" / "conversations" / "conversation-one" / "runs" / "run-one"
    )
    assert context.shared_dir == runtime_root / "user-one" / "shared"
    hermes_env = (context.hermes_home / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=user-deepseek-key" in hermes_env
    assert "OPENAI_BASE_URL=https://api.deepseek.com/v1" in hermes_env
    expected_browser_cache = shell_path(context.shared_dir / "playwright-browsers")
    assert f"PLAYWRIGHT_BROWSERS_PATH={expected_browser_cache}" in hermes_env
    hermes_config = (context.hermes_home / "config.yaml").read_text(encoding="utf-8")
    assert 'default: "deepseek-chat"' in hermes_config
    assert 'api_key: "user-deepseek-key"' in hermes_config

    scrub_runtime_credentials(context)
    assert not (context.hermes_home / ".env").exists()
    assert not (context.hermes_home / "config.yaml").exists()


def test_build_user_runtime_context_resumes_latest_conversation_session(
    monkeypatch, tmp_path: Path
):
    runtime_root = tmp_path / "runtime-users"
    hermes_home = _base_hermes_home(tmp_path)
    monkeypatch.setattr(settings, "agent_runtime_user_root", str(runtime_root))
    monkeypatch.setattr(settings, "hermes_home", str(hermes_home))
    monkeypatch.setattr(settings, "hermes_skills_dir", "")

    user = SimpleNamespace(id="user-one", username="Test User")
    first = build_user_runtime_context(user, "conversation-one", run_id="run-one")
    session_path = first.hermes_home / "sessions" / "session_previous-123.json"
    session_path.parent.mkdir(parents=True)
    session_path.write_text('{"messages": []}', encoding="utf-8")
    with sqlite3.connect(first.hermes_home / "state.db") as connection:
        connection.execute(
            "CREATE TABLE sessions ("
            "id TEXT PRIMARY KEY, message_count INTEGER, started_at REAL, ended_at REAL)"
        )
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?)",
            ("previous-123", 8, 1.0, 2.0),
        )

    second = build_user_runtime_context(user, "conversation-one", run_id="run-two")

    assert second.hermes_resume_session_id == "previous-123"
    assert second.hermes_home == first.hermes_home
    assert second.root_dir != first.root_dir
    assert (second.hermes_home / "sessions" / session_path.name).is_file()
    with sqlite3.connect(second.hermes_home / "state.db") as connection:
        assert connection.execute("SELECT id FROM sessions").fetchone() == (
            "previous-123",
        )


def test_adapter_lock_scope_respects_configured_scope(monkeypatch):
    monkeypatch.setattr(settings, "agent_adapter_limit_scope", "per_user")
    assert adapter_lock_scope("conversation:user:abc") == "conversation:user:abc"
    monkeypatch.setattr(settings, "agent_adapter_limit_scope", "global")
    assert adapter_lock_scope("conversation:user:abc") == "global"
