from pathlib import Path
from types import SimpleNamespace

from app.core.config import settings
from app.services.adapter_limiter import adapter_lock_scope
from app.services.agent_runtime_context import (
    build_user_runtime_context,
    safe_runtime_segment,
)


def test_safe_runtime_segment_strips_path_unsafe_characters():
    assert safe_runtime_segment("user/with\\slashes and spaces") == "user-with-slashes and spaces"
    assert safe_runtime_segment("../") == "user"


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
    (hermes_skills / "skill.txt").write_text("hermes skill", encoding="utf-8")
    (openclaw_skills / "skill.txt").write_text("openclaw skill", encoding="utf-8")

    monkeypatch.setattr(settings, "agent_runtime_user_root", str(runtime_root))
    monkeypatch.setattr(settings, "hermes_home", str(hermes_home))
    monkeypatch.setattr(settings, "hermes_skills_dir", "")
    monkeypatch.setattr(settings, "openclaw_skills_dir", str(openclaw_skills))

    user = SimpleNamespace(id="user/one", username="Test User")
    context = build_user_runtime_context(user, "conversation/one")

    assert context.root_dir == runtime_root / "user-one" / "conversations" / "conversation-one"
    assert context.hermes_home.exists()
    assert context.openclaw_home.exists()
    assert (context.hermes_skills_dir / "skill.txt").read_text(encoding="utf-8") == "hermes skill"
    openclaw_skill = (context.openclaw_skills_dir / "skill.txt").read_text(encoding="utf-8")
    assert openclaw_skill == "openclaw skill"
    assert context.adapter_lock_scope() == "conversation:user-one:conversation-one"


def test_adapter_lock_scope_respects_configured_scope(monkeypatch):
    monkeypatch.setattr(settings, "agent_adapter_limit_scope", "per_user")
    assert adapter_lock_scope("conversation:user:abc") == "conversation:user:abc"

    monkeypatch.setattr(settings, "agent_adapter_limit_scope", "global")
    assert adapter_lock_scope("conversation:user:abc") == "global"
