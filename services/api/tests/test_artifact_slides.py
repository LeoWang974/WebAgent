from pathlib import Path

from app.api.routes.artifacts import (
    dedupe_slide_artifacts,
    discover_deck_slide_paths,
    is_deck_slide_artifact,
    slides_from_paths,
)
from app.models import Artifact


def test_discover_deck_slide_paths_finds_png_pages(tmp_path: Path):
    deck = tmp_path / "deck.pptx"
    pages = tmp_path / "pages"
    pages.mkdir()
    deck.write_bytes(b"pptx")
    (pages / "page_002.png").write_bytes(b"png-two")
    (pages / "page_001.png").write_bytes(b"png-one")
    (pages / "page_001.prompt.txt").write_text("prompt", encoding="utf-8")
    (tmp_path / "report-preview.html").write_text("<html>report</html>", encoding="utf-8")

    artifact = Artifact(
        conversation_id="session_1",
        title="deck",
        type="ppt_deck",
        status="ready",
        artifact_metadata={"path": str(deck)},
    )

    paths = discover_deck_slide_paths(artifact)

    assert [path.name for path in paths] == ["page_001.png", "page_002.png"]


def test_discover_deck_slide_paths_dedupes_archived_and_source_pages(tmp_path: Path):
    deck = tmp_path / "deck.pptx"
    pages = tmp_path / "pages"
    source = tmp_path / "source" / "pages"
    pages.mkdir()
    source.mkdir(parents=True)
    deck.write_bytes(b"pptx")
    (pages / "page_001-archive.html").write_text("<html>archive 1</html>", encoding="utf-8")
    (pages / "page_002-archive.html").write_text("<html>archive 2</html>", encoding="utf-8")
    (source / "page_001.html").write_text("<html>source 1</html>", encoding="utf-8")
    (source / "page_002.html").write_text("<html>source 2</html>", encoding="utf-8")

    artifact = Artifact(
        conversation_id="session_1",
        title="deck",
        type="ppt_deck",
        status="ready",
        artifact_metadata={
            "path": str(deck),
            "sourceDir": str(source.parent),
        },
    )

    paths = discover_deck_slide_paths(artifact)

    assert [path.name for path in paths] == ["page_001-archive.html", "page_002-archive.html"]


def test_dedupe_slide_artifacts_keeps_one_artifact_per_page():
    first = Artifact(
        conversation_id="session_1",
        title="page_001-archive",
        type="html_page",
        status="ready",
        artifact_metadata={"filename": "page_001-archive.html"},
    )
    duplicate = Artifact(
        conversation_id="session_1",
        title="page_001",
        type="html_page",
        status="ready",
        artifact_metadata={"filename": "page_001.html"},
    )
    second = Artifact(
        conversation_id="session_1",
        title="page_002-archive",
        type="html_page",
        status="ready",
        artifact_metadata={"filename": "page_002-archive.html"},
    )

    assert dedupe_slide_artifacts([first, duplicate, second]) == [first, second]


def test_slides_from_png_paths_returns_html_wrapped_images(tmp_path: Path):
    slide = tmp_path / "page_001.png"
    slide.write_bytes(b"fake image bytes")
    artifact = Artifact(
        conversation_id="session_1",
        title="deck",
        type="ppt_deck",
        status="ready",
    )
    artifact.id = "artifact_1"

    slides = slides_from_paths(artifact, [slide])

    assert len(slides) == 1
    assert slides[0].content_type == "text/html"
    assert "data:image/png;base64," in (slides[0].content or "")
    assert slides[0].title == "page_001"


def test_is_deck_slide_artifact_rejects_report_html():
    report = Artifact(
        conversation_id="session_1",
        title="market-report",
        type="html_page",
        status="ready",
        artifact_metadata={"filename": "market-report.html"},
    )
    slide = Artifact(
        conversation_id="session_1",
        title="page_002",
        type="html_page",
        status="ready",
        artifact_metadata={"filename": "page_002.html"},
    )

    assert not is_deck_slide_artifact(report)
    assert is_deck_slide_artifact(slide)
