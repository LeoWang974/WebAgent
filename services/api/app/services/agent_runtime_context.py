import re
import shutil
from dataclasses import dataclass
from os import name as os_name
from pathlib import Path

from app.core.config import settings
from app.models import User
from app.services.skills_updater import default_openclaw_skills_dir


def safe_runtime_segment(value: str, fallback: str = "user") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value).strip(" .-")
    return cleaned[:96] or fallback


def runtime_root() -> Path:
    root = Path(settings.agent_runtime_user_root)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[4] / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def runtime_conversation_dir(user: User, conversation_id: str | None = None) -> Path:
    user_segment = safe_runtime_segment(user.id, "user")
    conversation_segment = safe_runtime_segment(conversation_id or "default", "conversation")
    path = runtime_root() / user_segment / "conversations" / conversation_segment
    path.mkdir(parents=True, exist_ok=True)
    return path


def _copy_skills_once(source: Path, destination: Path) -> Path:
    if destination.exists():
        return destination
    if source.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git"))
    else:
        destination.mkdir(parents=True, exist_ok=True)
    return destination


def _copy_file_once(source: Path, destination: Path) -> None:
    if not source.exists() or not source.is_file():
        return
    if destination.exists() and destination.read_bytes() == source.read_bytes():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def shell_path(path: Path) -> str:
    resolved = path.resolve()
    if os_name != "nt":
        return resolved.as_posix()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix().split(":", maxsplit=1)[1].lstrip("/")
    return f"/mnt/{drive}/{rest}"


@dataclass(frozen=True)
class UserRuntimeContext:
    user_id: str
    conversation_id: str
    root_dir: Path
    hermes_home: Path
    hermes_skills_dir: Path
    openclaw_home: Path
    openclaw_skills_dir: Path

    def adapter_lock_scope(self) -> str:
        user_segment = safe_runtime_segment(self.user_id)
        conversation_segment = safe_runtime_segment(self.conversation_id, "conversation")
        return f"conversation:{user_segment}:{conversation_segment}"

    def hermes_home_for_shell(self) -> str:
        return shell_path(self.hermes_home)

    def hermes_skills_dir_for_shell(self) -> str:
        return shell_path(self.hermes_skills_dir)

    def openclaw_home_for_shell(self) -> str:
        return shell_path(self.openclaw_home)

    def openclaw_skills_dir_for_shell(self) -> str:
        return shell_path(self.openclaw_skills_dir)


def build_user_runtime_context(
    user: User,
    conversation_id: str | None = None,
) -> UserRuntimeContext:
    root = runtime_conversation_dir(user, conversation_id)
    hermes_home = root / "hermes-home"
    openclaw_home = root / "openclaw-home"
    hermes_home.mkdir(parents=True, exist_ok=True)
    openclaw_home.mkdir(parents=True, exist_ok=True)
    _copy_file_once(Path(settings.hermes_home) / ".env", hermes_home / ".env")
    _copy_file_once(Path.home() / ".openclaw" / ".env", openclaw_home / ".openclaw" / ".env")

    hermes_source = (
        Path(settings.hermes_skills_dir)
        if settings.hermes_skills_dir
        else Path(settings.hermes_home) / "skills"
    )
    hermes_skills_dir = hermes_home / "skills"
    if hermes_source.exists():
        _copy_skills_once(hermes_source, hermes_skills_dir)
    else:
        hermes_skills_dir.mkdir(parents=True, exist_ok=True)

    openclaw_source = (
        Path(settings.openclaw_skills_dir)
        if settings.openclaw_skills_dir
        else default_openclaw_skills_dir()
    )
    openclaw_skills_dir = _copy_skills_once(openclaw_source, openclaw_home / "skills")

    return UserRuntimeContext(
        user_id=user.id,
        conversation_id=conversation_id or "default",
        root_dir=root,
        hermes_home=hermes_home,
        hermes_skills_dir=hermes_skills_dir,
        openclaw_home=openclaw_home,
        openclaw_skills_dir=openclaw_skills_dir,
    )
