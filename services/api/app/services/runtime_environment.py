# File purpose: Implements the runtime environment backend service workflow.
# Main declarations: safe_runtime_segment handles safe runtime segment; path_from_runtime_setting
# handles path from runtime setting; runtime_root handles runtime root; runtime_user_shared_dir
# handles runtime user shared dir; runtime_conversation_dir handles runtime conversation dir;
# runtime_conversation_dir_for_ids handles runtime conversation dir for ids; runtime_run_dir
# handles runtime run dir; runtime_run_dir_for_ids handles runtime run dir for ids;
# _restrict_private_file handles restrict private file; _copy_file handles copy file; _copy_skills
# handles copy skills; _read_env_file handles read env file; _write_runtime_env_values handles
# write runtime env values; _sync_runtime_env handles sync runtime env; _ensure_hermes_config
# handles ensure hermes config; shell_path handles shell path; UserRuntimeContext defines user
# runtime context state or behavior; _stage_latest_hermes_session handles stage latest hermes
# session; scrub_runtime_credentials handles scrub runtime credentials; build_user_runtime_context
# builds user runtime context.

import logging
import re
import shutil
import sqlite3
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


def runtime_user_shared_dir(user_id: str) -> Path:
    path = runtime_root() / safe_runtime_segment(user_id, "user") / "shared"
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_conversation_dir(user: User, conversation_id: str | None = None) -> Path:
    return runtime_conversation_dir_for_ids(user.id, conversation_id)


def runtime_conversation_dir_for_ids(
    user_id: str,
    conversation_id: str | None = None,
) -> Path:
    user_segment = safe_runtime_segment(user_id, "user")
    conversation_segment = safe_runtime_segment(conversation_id or "default", "conversation")
    path = runtime_root() / user_segment / "conversations" / conversation_segment
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_run_dir(
    user: User,
    conversation_id: str | None = None,
    run_id: str | None = None,
) -> Path:
    return runtime_run_dir_for_ids(user.id, conversation_id, run_id)


def runtime_run_dir_for_ids(
    user_id: str,
    conversation_id: str | None = None,
    run_id: str | None = None,
) -> Path:
    conversation_dir = runtime_conversation_dir_for_ids(user_id, conversation_id)
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
    shared_dir: Path,
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
    cache_dirs = {
        "XDG_CACHE_HOME": shared_dir / "xdg-cache",
        "PIP_CACHE_DIR": shared_dir / "pip-cache",
        "npm_config_cache": shared_dir / "npm-cache",
        "PLAYWRIGHT_BROWSERS_PATH": shared_dir / "playwright-browsers",
        "PYTHONUSERBASE": shared_dir / "python-user-base",
    }
    for directory in cache_dirs.values():
        directory.mkdir(parents=True, exist_ok=True)
    values.update({key: shell_path(path) for key, path in cache_dirs.items()})
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
    shared_dir: Path
    hermes_home: Path
    hermes_skills_dir: Path
    hermes_resume_session_id: str | None = None

    def adapter_lock_scope(self) -> str:
        return runtime_adapter_lock_scope(self.user_id, self.conversation_id)

    def hermes_home_for_shell(self) -> str:
        return shell_path(self.hermes_home)


def runtime_adapter_lock_scope(
    user_id: str,
    conversation_id: str | None = None,
) -> str:
    user_segment = safe_runtime_segment(user_id)
    conversation_segment = safe_runtime_segment(conversation_id or "", "conversation")
    return f"conversation:{user_segment}:{conversation_segment}"


def _stage_latest_hermes_session(
    conversation_dir: Path,
    current_run_dir: Path,
    hermes_home: Path,
) -> str | None:
    runs_dir = conversation_dir / "runs"
    if not runs_dir.is_dir():
        return None

    candidates = [
        path
        for path in runs_dir.glob("*/hermes-home/sessions/session_*.json")
        if current_run_dir not in path.parents and path.is_file()
    ]
    if not candidates:
        return None

    viable_sessions: list[tuple[float, float, int, Path, Path]] = []
    for candidate in candidates:
        candidate_session_id = candidate.stem.removeprefix("session_")
        candidate_state_db = candidate.parent.parent / "state.db"
        if not candidate_state_db.is_file():
            continue
        try:
            with sqlite3.connect(candidate_state_db) as source_connection:
                session_row = source_connection.execute(
                    "SELECT message_count, COALESCE(ended_at, started_at, 0) "
                    "FROM sessions WHERE id = ? LIMIT 1",
                    (candidate_session_id,),
                ).fetchone()
        except sqlite3.Error:
            logger.debug(
                "Unable to inspect Hermes state database %s",
                candidate_state_db,
                exc_info=True,
            )
            continue
        if session_row:
            viable_sessions.append(
                (
                    candidate.stat().st_mtime,
                    float(session_row[1] or 0),
                    int(session_row[0] or 0),
                    candidate,
                    candidate_state_db,
                )
            )

    if not viable_sessions:
        return None

    _, _, _, latest, source_state_db = max(viable_sessions)

    destination = hermes_home / "sessions" / latest.name
    _copy_file(latest, destination)
    destination_state_db = hermes_home / "state.db"
    try:
        with (
            sqlite3.connect(source_state_db) as source_connection,
            sqlite3.connect(destination_state_db) as destination_connection,
        ):
            source_connection.backup(destination_connection)
    except sqlite3.Error:
        logger.warning(
            "Unable to stage Hermes state database from %s",
            source_state_db,
            exc_info=True,
        )
        return None
    return latest.stem.removeprefix("session_")


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
    conversation_dir = runtime_conversation_dir(user, conversation_id)
    shared_dir = runtime_user_shared_dir(user.id)
    # Hermes session state belongs to a conversation, while generated files and
    # process workspaces remain isolated by run. The per-conversation adapter
    # lock prevents concurrent processes from mutating this home at once.
    hermes_home = conversation_dir / "hermes-home"
    hermes_home.mkdir(parents=True, exist_ok=True)
    base_hermes_home = Path(settings.hermes_home).expanduser()
    _copy_file(base_hermes_home / ".env", hermes_home / ".env")
    _ensure_hermes_config(base_hermes_home, hermes_home, model_runtime_config)
    _sync_runtime_env(hermes_home / ".env", model_runtime_config, shared_dir)

    source_skills = (
        Path(settings.hermes_skills_dir)
        if settings.hermes_skills_dir
        else base_hermes_home / "skills"
    )
    hermes_skills_dir = hermes_home / "skills"
    _copy_skills(source_skills, hermes_skills_dir)
    resume_session_id = None
    if run_id:
        state_db = hermes_home / "state.db"
        if not state_db.is_file():
            resume_session_id = _stage_latest_hermes_session(
                conversation_dir,
                root,
                hermes_home,
            )
        else:
            sessions = sorted(
                (hermes_home / "sessions").glob("session_*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if sessions:
                resume_session_id = sessions[0].stem.removeprefix("session_")

    return UserRuntimeContext(
        user_id=user.id,
        conversation_id=conversation_id or "default",
        run_id=run_id,
        root_dir=root,
        shared_dir=shared_dir,
        hermes_home=hermes_home,
        hermes_skills_dir=hermes_skills_dir,
        hermes_resume_session_id=resume_session_id,
    )
