from pathlib import Path

from app.core.config import settings
from app.services import file_storage


def test_conversation_upload_dir_is_scoped_by_user(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(file_storage, "upload_storage_root", lambda: tmp_path / "uploads")

    first = file_storage.conversation_upload_dir("user/one", "conversation/one")
    second = file_storage.conversation_upload_dir("user/two", "conversation/one")

    assert first == (
        tmp_path
        / "uploads"
        / "users"
        / "user-one"
        / "conversations"
        / "conversation-one"
    )
    assert second != first


def test_remove_conversation_storage_removes_managed_directories(monkeypatch, tmp_path: Path):
    upload_root = tmp_path / "uploads"
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr(file_storage, "upload_storage_root", lambda: upload_root)
    monkeypatch.setattr(settings, "artifact_storage_root", str(artifact_root))

    upload_dir = file_storage.conversation_upload_dir("user-1", "conversation-1")
    artifact_dir = (
        artifact_root
        / "users"
        / "user-1"
        / "conversations"
        / "conversation-1"
    )
    artifact_dir.mkdir(parents=True)
    (upload_dir / "input.md").write_text("input", encoding="utf-8")
    (artifact_dir / "report.md").write_text("report", encoding="utf-8")

    file_storage.remove_conversation_storage("user-1", "conversation-1")

    assert not upload_dir.exists()
    assert not artifact_dir.exists()
