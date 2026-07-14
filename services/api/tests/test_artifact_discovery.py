from pathlib import Path

from app.services import mock_store
from app.services.artifact_discovery import (
    _normalized_path_key,
    create_artifacts_from_paths,
)


def test_normalized_path_key_unifies_windows_and_wsl_paths():
    assert _normalized_path_key(r"C:\Users\demo\report.md") == "/mnt/c/users/demo/report.md"
    assert (
        _normalized_path_key(r"\\wsl.localhost\Ubuntu\home\demo\report.md")
        == "/home/demo/report.md"
    )
    assert _normalized_path_key("/home/demo/report.md") == "/home/demo/report.md"


def test_create_artifacts_from_paths_dedupes_by_content_hash(tmp_path: Path):
    original_artifacts = list(mock_store.artifacts)
    try:
        mock_store.artifacts.clear()
        first = tmp_path / "report.md"
        second = tmp_path / "copy.md"
        first.write_text("# Report\nsame content", encoding="utf-8")
        second.write_text("# Report\nsame content", encoding="utf-8")

        artifacts = create_artifacts_from_paths("session_1", [str(first), str(second)])

        assert len(artifacts) == 1
        assert artifacts[0].type == "markdown_report"
        assert artifacts[0].content == "# Report\nsame content"
        assert artifacts[0].metadata
        assert artifacts[0].metadata["contentHash"]
    finally:
        mock_store.artifacts[:] = original_artifacts
