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
)


def test_safe_runtime_segment_strips_path_unsafe_characters():
    assert safe_runtime_segment("user/with\\slashes and spaces") == "user-with-slashes and spaces"
    assert safe_runtime_segment("../") == "user"


def test_path_from_runtime_setting_accepts_wsl_drive_path_on_windows(monkeypatch):
    monkeypatch.setattr("app.services.runtime_environment.os_name", "nt")

    path = path_from_runtime_setting("/mnt/d/gitWorkSpace/WebAgent/runtime/users")

    assert str(path) == r"D:\gitWorkSpace\WebAgent\runtime\users"


def test_build_user_runtime_context_creates_per_conversation_dirs(
    monkeypatch,
    tmp_path: Path,
):
    runtime_root = tmp_path / "runtime-users"
    hermes_home = tmp_path / "base-hermes"
    hermes_skills = hermes_home / "skills"
    openclaw_skills = tmp_path / "base-openclaw-skills"
    hermes_skills.mkdir(parents=True)
    openclaw_skills.mkdir(parents=True)
    (hermes_home / ".env").write_text("SERPER_API_KEY=test\n", encoding="utf-8")
    (hermes_home / "config.yaml").write_text(
        'model:\n  provider: "custom"\n  base_url: "https://token.sensenova.cn/v1"\n',
        encoding="utf-8",
    )
    (hermes_skills / "skill.txt").write_text("hermes skill", encoding="utf-8")
    (openclaw_skills / "skill.txt").write_text("openclaw skill", encoding="utf-8")

    monkeypatch.setattr(settings, "agent_runtime_user_root", str(runtime_root))
    monkeypatch.setattr(settings, "hermes_home", str(hermes_home))
    monkeypatch.setattr(settings, "hermes_skills_dir", "")
    monkeypatch.setattr(settings, "openclaw_skills_dir", str(openclaw_skills))
    monkeypatch.setattr(settings, "sensenova_api_key", "sensenova-test-key")
    monkeypatch.setattr(settings, "sensenova_base_url", "https://token.sensenova.cn/v1")

    user = SimpleNamespace(id="user/one", username="Test User")
    context = build_user_runtime_context(user, "conversation/one")

    assert context.root_dir == runtime_root / "user-one" / "conversations" / "conversation-one"
    assert context.hermes_home.exists()
    assert context.openclaw_home.exists()
    assert (context.hermes_skills_dir / "skill.txt").read_text(encoding="utf-8") == "hermes skill"
    hermes_env = (context.hermes_home / ".env").read_text(encoding="utf-8")
    assert "SERPER_API_KEY=test" in hermes_env
    assert "OPENAI_API_KEY=sensenova-test-key" in hermes_env
    assert "OPENAI_BASE_URL=https://token.sensenova.cn/v1" in hermes_env
    assert (context.hermes_home / "config.yaml").exists()
    assert 'provider: "custom"' in (context.hermes_home / "config.yaml").read_text(
        encoding="utf-8"
    )
    openclaw_skill = (context.openclaw_skills_dir / "skill.txt").read_text(encoding="utf-8")
    assert openclaw_skill == "openclaw skill"
    openclaw_env = (context.openclaw_home / ".openclaw" / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sensenova-test-key" in openclaw_env
    assert context.adapter_lock_scope() == "conversation:user-one:conversation-one"


def test_build_user_runtime_context_uses_run_model_snapshot(monkeypatch, tmp_path: Path):
    runtime_root = tmp_path / "runtime-users"
    hermes_home = tmp_path / "base-hermes"
    hermes_home.mkdir(parents=True)
    (hermes_home / ".env").write_text(
        (
            "OPENAI_API_KEY=global-key\n"
            "OPENAI_BASE_URL=https://global.example/v1\n"
            "GEMINI_API_KEY=stale-gemini-key\n"
        ),
        encoding="utf-8",
    )
    openclaw_home = tmp_path / "home"
    (openclaw_home / ".openclaw").mkdir(parents=True)
    (openclaw_home / ".openclaw" / ".env").write_text(
        "OPENAI_API_KEY=global-key\n",
        encoding="utf-8",
    )
    openclaw_skills = tmp_path / "base-openclaw-skills"
    openclaw_skills.mkdir(parents=True)

    monkeypatch.setattr(settings, "agent_runtime_user_root", str(runtime_root))
    monkeypatch.setattr(settings, "hermes_home", str(hermes_home))
    monkeypatch.setattr(settings, "hermes_skills_dir", "")
    monkeypatch.setattr(settings, "openclaw_skills_dir", str(openclaw_skills))
    monkeypatch.setattr(Path, "home", lambda: openclaw_home)

    model_runtime_config = ModelRuntimeConfig(
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
        model_runtime_config=model_runtime_config,
    )

    assert context.root_dir == (
        runtime_root / "user-one" / "conversations" / "conversation-one" / "runs" / "run-one"
    )
    hermes_env = (context.hermes_home / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=user-deepseek-key" in hermes_env
    assert "OPENAI_BASE_URL=https://api.deepseek.com/v1" in hermes_env
    assert "OPENAI_API_KEY=global-key" not in hermes_env
    assert "GEMINI_API_KEY=stale-gemini-key" not in hermes_env
    hermes_config = (context.hermes_home / "config.yaml").read_text(encoding="utf-8")
    assert 'default: "deepseek-chat"' in hermes_config
    assert 'base_url: "https://api.deepseek.com/v1"' in hermes_config
    openclaw_env = (context.openclaw_home / ".openclaw" / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=user-deepseek-key" in openclaw_env

    scrub_runtime_credentials(context)

    assert not (context.hermes_home / ".env").exists()
    assert not (context.openclaw_home / ".openclaw" / ".env").exists()
    assert not (context.openclaw_home / ".openclaw" / "openclaw.json").exists()


def test_adapter_lock_scope_respects_configured_scope(monkeypatch):
    monkeypatch.setattr(settings, "agent_adapter_limit_scope", "per_user")
    assert adapter_lock_scope("conversation:user:abc") == "conversation:user:abc"

    monkeypatch.setattr(settings, "agent_adapter_limit_scope", "global")
    assert adapter_lock_scope("conversation:user:abc") == "global"
