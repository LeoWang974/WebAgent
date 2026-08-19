# File purpose: Implements the file storage backend service workflow.
# Main declarations: upload_storage_root handles upload storage root; conversation_upload_dir
# handles conversation upload dir; user_global_upload_dir handles user global upload dir;
# remove_conversation_storage removes conversation storage.

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
        # Legacy path for uploads created before storage became user-scoped.
        upload_storage_root() / safe_storage_segment(conversation_id, "conversation"),
    )
    for path in (artifact_dir, *upload_dirs):
        try:
            shutil.rmtree(path, ignore_errors=False)
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("Unable to remove conversation storage: %s", path, exc_info=True)
