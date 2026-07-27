import re
from pathlib import Path

from app.core.config import settings


def safe_run_path_segment(value: str, fallback: str = "run") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value).strip(" .-")
    return cleaned[:96] or fallback


def run_workspace_dir(
    run_id: str,
    conversation_id: str | None = None,
    user_id: str | None = None,
) -> Path:
    root = Path(settings.agent_run_workspace_root)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[4] / root
    user_part = safe_run_path_segment(user_id or "anonymous", "user")
    conversation_part = safe_run_path_segment(conversation_id or "conversation")
    run_part = safe_run_path_segment(run_id)
    path = root / user_part / conversation_part / run_part
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_artifacts_dir(
    run_id: str,
    conversation_id: str | None = None,
    user_id: str | None = None,
) -> Path:
    path = run_workspace_dir(run_id, conversation_id, user_id) / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path
