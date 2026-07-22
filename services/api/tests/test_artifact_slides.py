from pathlib import Path

from app.api.routes.artifacts import discover_deck_slide_paths, slides_from_paths
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
