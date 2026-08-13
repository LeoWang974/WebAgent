import logging
import shutil
from pathlib import Path

from app.services.artifact_storage import artifact_storage_root, safe_storage_segment

logger = logging.getLogger(__name__)


def upload_storage_root() -> Path:
    root = Path(__file__).resolve().parents[4] / "runtime" / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def conversation_upload_dir(user_id: str, conversation_id: str) -> Path:
    path = (
        upload_storage_root()
        / "users"
        / safe_storage_segment(user_id, "user")
        / "conversations"
        / safe_storage_segment(conversation_id, "conversation")
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_global_upload_dir(user_id: str) -> Path:
    path = upload_storage_root() / "users" / safe_storage_segment(user_id, "user") / "global"
    path.mkdir(parents=True, exist_ok=True)
    return path


def remove_conversation_storage(user_id: str, conversation_id: str) -> None:
    artifact_dir = (
        artifact_storage_root()
        / "users"
        / safe_storage_segment(user_id, "user")
        / "conversations"
        / safe_storage_segment(conversation_id, "conversation")
    )
    upload_dirs = (
        upload_storage_root()
        / "users"
        / safe_storage_segment(user_id, "user")
        / "conversations"
        / safe_storage_segment(conversation_id, "conversation"),
        upload_storage_root() / safe_storage_segment(conversation_id, "conversation"),
    )
    for path in (artifact_dir, *upload_dirs):
        try:
            shutil.rmtree(path, ignore_errors=False)
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("Unable to remove conversation storage: %s", path, exc_info=True)
