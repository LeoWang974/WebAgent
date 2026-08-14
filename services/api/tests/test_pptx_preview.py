from pathlib import Path

from app.core.config import settings
from app.services import pptx_preview


def test_find_soffice_uses_configured_binary(tmp_path: Path, monkeypatch):
    executable = tmp_path / "soffice"
    executable.write_bytes(b"")
    monkeypatch.setattr(settings, "libreoffice_path", str(executable))

    assert pptx_preview.find_soffice() == executable.resolve()


def test_render_pptx_preview_builds_and_reuses_cache(tmp_path: Path, monkeypatch):
    source = tmp_path / "deck.pptx"
    source.write_bytes(b"pptx content")
    cache_root = tmp_path / "cache"
    conversion_calls = 0
    rendering_calls = 0

    def fake_convert(_source: Path, work_dir: Path) -> Path:
        nonlocal conversion_calls
        conversion_calls += 1
        pdf_path = work_dir / "presentation.pdf"
        pdf_path.write_bytes(b"pdf")
        return pdf_path

    def fake_render(_pdf: Path, output_dir: Path) -> list[Path]:
        nonlocal rendering_calls
        rendering_calls += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = [output_dir / "page_001.png", output_dir / "page_002.png"]
        for path in paths:
            path.write_bytes(b"png")
        return paths

    monkeypatch.setattr(settings, "artifact_preview_cache_root", str(cache_root))
    monkeypatch.setattr(pptx_preview, "_convert_pptx_to_pdf", fake_convert)
    monkeypatch.setattr(pptx_preview, "_render_pdf_to_pngs", fake_render)

    first = pptx_preview.render_pptx_preview(source)
    second = pptx_preview.render_pptx_preview(source)

    assert [path.name for path in first] == ["page_001.png", "page_002.png"]
    assert second == first
    assert conversion_calls == 1
    assert rendering_calls == 1
