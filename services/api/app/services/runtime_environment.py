import logging
import re
import shutil
from dataclasses import dataclass
from os import environ
from os import name as os_name
from pathlib import Path

from app.core.config import settings
from app.models import User
from app.services.model_runtime_config import ModelRuntimeConfig

logger = logging.getLogger(__name__)
MANAGED_ENV_COMMENT = "# Managed by WebAgent runtime context."


def safe_runtime_segment(value: str, fallback: str = "user") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value).strip(" .-")
    return cleaned[:96] or fallback


def path_from_runtime_setting(value: str) -> Path:
    normalized = value.strip().replace("\\", "/")
    if os_name == "nt":
        match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", normalized)
        if match:
            drive = match.group(1).upper()
            rest = match.group(2).replace("/", "\\")
            return Path(f"{drive}:\\{rest}")
    return Path(value).expanduser()


def runtime_root() -> Path:
    root = path_from_runtime_setting(settings.agent_runtime_user_root)
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


def runtime_run_dir(
    user: User,
    conversation_id: str | None = None,
    run_id: str | None = None,
) -> Path:
    conversation_dir = runtime_conversation_dir(user, conversation_id)
    if not run_id:
        return conversation_dir
    path = conversation_dir / "runs" / safe_runtime_segment(run_id, "run")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _restrict_private_file(path: Path) -> None:
    if not path.is_file():
        return
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_skills(source: Path, destination: Path) -> None:
    if destination.exists():
        return
    if source.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns(".git"),
            dirs_exist_ok=True,
        )
    else:
        destination.mkdir(parents=True, exist_ok=True)


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            values[key] = value.strip().strip("'\"")
    return values


def _write_runtime_env_values(path: Path, values: dict[str, str | None]) -> None:
    managed_keys = set(values)
    existing_lines = (
        path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if path.exists()
        else []
    )
    preserved_lines: list[str] = []
    for raw_line in existing_lines:
        line = raw_line.strip()
        if line == MANAGED_ENV_COMMENT:
            continue
        if not line or line.startswith("#") or "=" not in line:
            preserved_lines.append(raw_line)
            continue
        if line.split("=", 1)[0].strip() not in managed_keys:
            preserved_lines.append(raw_line)

    populated = {key: value for key, value in values.items() if value}
    while preserved_lines and not preserved_lines[-1].strip():
        preserved_lines.pop()
    if populated:
        if preserved_lines:
            preserved_lines.append("")
        preserved_lines.append(MANAGED_ENV_COMMENT)
        for key in sorted(populated):
            value = str(populated[key]).replace("\n", "").replace("\r", "")
            preserved_lines.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(preserved_lines) + "\n", encoding="utf-8")
    _restrict_private_file(path)


def _sync_runtime_env(
    hermes_env_path: Path,
    model_runtime_config: ModelRuntimeConfig | None,
) -> None:
    existing = _read_env_file(hermes_env_path)
    if model_runtime_config is not None:
        values = model_runtime_config.env_values()
    else:
        api_key = settings.sensenova_api_key or environ.get("SENSENOVA_API_KEY")
        base_url = settings.sensenova_base_url or environ.get("SENSENOVA_BASE_URL")
        values = {
            "SENSENOVA_API_KEY": api_key,
            "SENSENOVA_BASE_URL": base_url,
            "OPENAI_API_KEY": api_key,
            "OPENAI_BASE_URL": base_url,
            "SN_API_KEY": api_key,
            "SN_BASE_URL": base_url,
            "SN_CHAT_API_KEY": api_key,
            "SN_TEXT_API_KEY": api_key,
        }
    values["SERPER_API_KEY"] = (
        values.get("SERPER_API_KEY")
        or existing.get("SERPER_API_KEY")
        or environ.get("SERPER_API_KEY")
    )
    _write_runtime_env_values(hermes_env_path, values)


def _ensure_hermes_config(
    source_home: Path,
    destination_home: Path,
    model_runtime_config: ModelRuntimeConfig | None,
) -> None:
    destination = destination_home / "config.yaml"
    if model_runtime_config is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(model_runtime_config.hermes_config_yaml(), encoding="utf-8")
        _restrict_private_file(destination)
        return
    source = source_home / "config.yaml"
    if source.is_file():
        _copy_file(source, destination)


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
    run_id: str | None
    root_dir: Path
    hermes_home: Path
    hermes_skills_dir: Path

    def adapter_lock_scope(self) -> str:
        user_segment = safe_runtime_segment(self.user_id)
        conversation_segment = safe_runtime_segment(self.conversation_id, "conversation")
        return f"conversation:{user_segment}:{conversation_segment}"

    def hermes_home_for_shell(self) -> str:
        return shell_path(self.hermes_home)

    def hermes_skills_dir_for_shell(self) -> str:
        return shell_path(self.hermes_skills_dir)


def scrub_runtime_credentials(context: UserRuntimeContext) -> None:
    for credential_path in (
        context.hermes_home / ".env",
        context.hermes_home / "config.yaml",
    ):
        try:
            credential_path.unlink(missing_ok=True)
        except OSError as error:
            logger.warning(
                "Unable to remove runtime credential file %s: %s",
                credential_path,
                error,
            )


def build_user_runtime_context(
    user: User,
    conversation_id: str | None = None,
    run_id: str | None = None,
    model_runtime_config: ModelRuntimeConfig | None = None,
) -> UserRuntimeContext:
    root = runtime_run_dir(user, conversation_id, run_id)
    hermes_home = root / "hermes-home"
    hermes_home.mkdir(parents=True, exist_ok=True)
    base_hermes_home = Path(settings.hermes_home).expanduser()
    _copy_file(base_hermes_home / ".env", hermes_home / ".env")
    _ensure_hermes_config(base_hermes_home, hermes_home, model_runtime_config)
    _sync_runtime_env(hermes_home / ".env", model_runtime_config)

    source_skills = (
        Path(settings.hermes_skills_dir)
        if settings.hermes_skills_dir
        else base_hermes_home / "skills"
    )
    hermes_skills_dir = hermes_home / "skills"
    _copy_skills(source_skills, hermes_skills_dir)

    return UserRuntimeContext(
        user_id=user.id,
        conversation_id=conversation_id or "default",
        run_id=run_id,
        root_dir=root,
        hermes_home=hermes_home,
        hermes_skills_dir=hermes_skills_dir,
    )
