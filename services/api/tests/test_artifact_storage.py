# File purpose: Verifies durable artifact storage avoids redundant file hashing.
# Main declarations: test_store_artifact_file_reuses_verified_hash checks verified hash reuse.

from pathlib import Path

from app.core.config import settings
from app.services import artifact_storage


def test_store_artifact_file_reuses_verified_hash(tmp_path, monkeypatch):
    source = tmp_path / "report.pptx"
    source.write_bytes(b"pptx payload")
    verified_hash = "a" * 64
    monkeypatch.setattr(settings, "artifact_storage_root", str(tmp_path / "artifacts"))

    def fail_if_rehashed(_path: Path) -> str:
        raise AssertionError("verified artifact content must not be hashed again")

    monkeypatch.setattr(artifact_storage, "file_sha256", fail_if_rehashed)

    stored = artifact_storage.store_artifact_file(
        source,
        user_id="user-1",
        conversation_id="conversation-1",
        run_id="run-1",
        is_primary=True,
        content_hash=verified_hash,
    )

    assert stored.content_hash == verified_hash
    assert stored.path.name == f"report-{verified_hash[:12]}.pptx"
    assert stored.path.read_bytes() == b"pptx payload"
