import json
import re
import shutil
from dataclasses import dataclass
from os import environ
from os import name as os_name
from pathlib import Path

from app.core.config import settings
from app.models import User
from app.services.model_runtime_config import ModelRuntimeConfig
from app.services.skills_updater import default_openclaw_skills_dir


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


def runtime_shared_dir() -> Path:
    path = runtime_root() / "_shared"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
    run_segment = safe_runtime_segment(run_id, "run")
    path = conversation_dir / "runs" / run_segment
    path.mkdir(parents=True, exist_ok=True)
    return path


def _copy_skills_once(source: Path, destination: Path) -> Path:
    if destination.exists():
        return destination
    try:
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
    except FileExistsError:
        return destination
    return destination


def _copy_file_once(source: Path, destination: Path) -> None:
    if not source.exists() or not source.is_file():
        return
    if destination.exists() and destination.read_bytes() == source.read_bytes():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _sync_openclaw_config(source_home: Path, destination_home: Path) -> None:
    for relative_path in (
        Path(".openclaw") / "openclaw.json",
        Path(".openclaw") / ".env",
    ):
        _copy_file_once(source_home / relative_path, destination_home / relative_path)
    _write_runtime_env_values(
        destination_home / ".openclaw" / ".env",
        _openclaw_gateway_env_values(destination_home / ".openclaw" / "openclaw.json"),
    )


def _openclaw_gateway_env_values(config_path: Path) -> dict[str, str | None]:
    values: dict[str, str | None] = {
        "OPENCLAW_GATEWAY_URL": environ.get("OPENCLAW_GATEWAY_URL"),
    }
    if not config_path.exists():
        return values
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return values
    gateway = config.get("gateway") if isinstance(config, dict) else None
    auth = gateway.get("auth") if isinstance(gateway, dict) else None
    token = auth.get("token") if isinstance(auth, dict) else None
    if isinstance(token, str) and token.strip():
        values.update(
            {
                "OPENCLAW_GATEWAY_TOKEN": token.strip(),
                "OPENCLAW_GATEWAY_AUTH_TOKEN": token.strip(),
                "OPENCLAW_TOKEN": token.strip(),
            }
        )
    return values


def _ensure_shared_openclaw_skills(source: Path) -> Path:
    destination = runtime_shared_dir() / "openclaw-skills"
    return _copy_skills_once(source, destination)


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists() or not path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        values[key] = value.strip().strip("'\"")
    return values


def _write_runtime_env_values(path: Path, values: dict[str, str | None]) -> None:
    managed_keys = {key for key, value in values.items() if value}
    if not managed_keys:
        return

    existing_lines = (
        path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if path.exists()
        else []
    )
    preserved_lines: list[str] = []
    for raw_line in existing_lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            preserved_lines.append(raw_line)
            continue
        key = line.split("=", 1)[0].strip()
        if key not in managed_keys:
            preserved_lines.append(raw_line)

    path.parent.mkdir(parents=True, exist_ok=True)
    output_lines = preserved_lines
    if output_lines and output_lines[-1].strip():
        output_lines.append("")
    output_lines.append("# Managed by WebAgent runtime context.")
    for key in sorted(managed_keys):
        value = str(values[key]).replace("\n", "").replace("\r", "")
        output_lines.append(f"{key}={value}")
    path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def _sync_runtime_env(
    hermes_env_path: Path,
    openclaw_env_path: Path,
    model_runtime_config: ModelRuntimeConfig | None = None,
) -> None:
    if model_runtime_config is not None:
        common_values = model_runtime_config.env_values()
        _write_runtime_env_values(hermes_env_path, common_values)
        _write_runtime_env_values(openclaw_env_path, common_values)
        return

    sensenova_base_url = settings.sensenova_base_url or environ.get("SENSENOVA_BASE_URL")
    sensenova_api_key = settings.sensenova_api_key or environ.get("SENSENOVA_API_KEY")
    openai_base_url = sensenova_base_url or environ.get("OPENAI_BASE_URL")
    openai_api_key = sensenova_api_key or environ.get("OPENAI_API_KEY")
    existing_hermes_env = _read_env_file(hermes_env_path)
    existing_openclaw_env = _read_env_file(openclaw_env_path)
    serper_api_key = (
        existing_hermes_env.get("SERPER_API_KEY")
        or existing_openclaw_env.get("SERPER_API_KEY")
        or environ.get("SERPER_API_KEY")
    )

    common_values = {
        "SENSENOVA_API_KEY": sensenova_api_key,
        "SENSENOVA_BASE_URL": sensenova_base_url,
        "OPENAI_API_KEY": openai_api_key,
        "OPENAI_BASE_URL": openai_base_url,
        "SERPER_API_KEY": serper_api_key,
    }
    _write_runtime_env_values(hermes_env_path, common_values)
    _write_runtime_env_values(openclaw_env_path, common_values)


def _ensure_hermes_config(
    source_home: Path,
    destination_home: Path,
    model_runtime_config: ModelRuntimeConfig | None = None,
) -> None:
    source_config = source_home / "config.yaml"
    destination_config = destination_home / "config.yaml"
    if model_runtime_config is not None:
        destination_config.parent.mkdir(parents=True, exist_ok=True)
        destination_config.write_text(model_runtime_config.hermes_config_yaml(), encoding="utf-8")
        return

    if source_config.exists() and source_config.is_file():
        _copy_file_once(source_config, destination_config)
        return

    if destination_config.exists():
        return

    base_url = settings.sensenova_base_url or environ.get("SENSENOVA_BASE_URL")
    if not base_url:
        return

    destination_config.write_text(
        "\n".join(
            [
                "model:",
                f'  default: "{settings.sensenova_default_model}"',
                '  provider: "custom"',
                f'  base_url: "{base_url}"',
                "",
            ]
        ),
        encoding="utf-8",
    )


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
    run_id: str | None = None,
    model_runtime_config: ModelRuntimeConfig | None = None,
) -> UserRuntimeContext:
    root = runtime_run_dir(user, conversation_id, run_id)
    hermes_home = root / "hermes-home"
    openclaw_home = root / "openclaw-home"
    hermes_home.mkdir(parents=True, exist_ok=True)
    openclaw_home.mkdir(parents=True, exist_ok=True)
    base_hermes_home = Path(settings.hermes_home).expanduser()
    _copy_file_once(base_hermes_home / ".env", hermes_home / ".env")
    _ensure_hermes_config(base_hermes_home, hermes_home, model_runtime_config)
    _sync_openclaw_config(Path.home(), openclaw_home)
    _sync_runtime_env(
        hermes_home / ".env",
        openclaw_home / ".openclaw" / ".env",
        model_runtime_config,
    )

    hermes_source = (
        Path(settings.hermes_skills_dir)
        if settings.hermes_skills_dir
        else Path(settings.hermes_home).expanduser() / "skills"
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
    openclaw_skills_dir = _ensure_shared_openclaw_skills(openclaw_source)

    return UserRuntimeContext(
        user_id=user.id,
        conversation_id=conversation_id or "default",
        run_id=run_id,
        root_dir=root,
        hermes_home=hermes_home,
        hermes_skills_dir=hermes_skills_dir,
        openclaw_home=openclaw_home,
        openclaw_skills_dir=openclaw_skills_dir,
    )
