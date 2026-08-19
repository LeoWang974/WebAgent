# File purpose: Implements the pptx preview backend service workflow.
# Main declarations: PptxPreviewError defines pptx preview error state or behavior; _render_lock
# handles render lock; _file_sha256 handles file sha256; _preview_cache_root handles preview cache
# root; _cached_slide_paths handles cached slide paths; _soffice_candidates handles soffice
# candidates; find_soffice handles find soffice; _convert_pptx_to_pdf handles convert pptx to pdf;
# _render_pdf_to_pngs handles render pdf to pngs; render_pptx_preview renders pptx preview.

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from app.core.config import settings


class PptxPreviewError(RuntimeError):
    """Raised when a PPTX cannot be converted into browser preview images."""


_render_locks: dict[str, threading.Lock] = {}
_render_locks_guard = threading.Lock()


def _render_lock(cache_key: str) -> threading.Lock:
    with _render_locks_guard:
        return _render_locks.setdefault(cache_key, threading.Lock())


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _preview_cache_root() -> Path:
    root = Path(settings.artifact_preview_cache_root).expanduser()
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[4] / root
    return root.resolve()


def _cached_slide_paths(cache_dir: Path) -> list[Path]:
    return sorted(cache_dir.glob("page_*.png")) if cache_dir.is_dir() else []


def _soffice_candidates() -> list[Path]:
    configured = settings.libreoffice_path.strip() if settings.libreoffice_path else ""
    candidates = [Path(configured)] if configured else []
    for command in ("soffice", "libreoffice"):
        resolved = shutil.which(command)
        if resolved:
            candidates.append(Path(resolved))
    if os.name == "nt":
        for environment_name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            program_files = os.environ.get(environment_name)
            if program_files:
                candidates.append(Path(program_files) / "LibreOffice" / "program" / "soffice.com")
                candidates.append(Path(program_files) / "LibreOffice" / "program" / "soffice.exe")
    return candidates


def find_soffice() -> Path | None:
    for candidate in _soffice_candidates():
        if candidate.is_file():
            return candidate.resolve()
    return None


def _convert_pptx_to_pdf(pptx_path: Path, work_dir: Path) -> Path:
    soffice = find_soffice()
    if soffice is None:
        raise PptxPreviewError(
            "LibreOffice is not installed. Install LibreOffice Impress or set LIBREOFFICE_PATH."
        )

    input_path = work_dir / "presentation.pptx"
    output_dir = work_dir / "pdf"
    profile_dir = work_dir / "libreoffice-profile"
    output_dir.mkdir(parents=True)
    profile_dir.mkdir()
    shutil.copy2(pptx_path, input_path)
    profile_url = profile_dir.resolve().as_uri()

    command = [
        str(soffice),
        f"-env:UserInstallation={profile_url}",
        "--headless",
        "--nologo",
        "--nodefault",
        "--nofirststartwizard",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(input_path),
    ]
    environment = os.environ.copy()
    environment.setdefault("SAL_USE_VCLPLUGIN", "svp")
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            env=environment,
            text=True,
            timeout=settings.pptx_preview_timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise PptxPreviewError(
            f"LibreOffice did not finish within {settings.pptx_preview_timeout_seconds} seconds."
        ) from error
    except OSError as error:
        raise PptxPreviewError(f"LibreOffice could not be started: {error}") from error

    pdf_path = output_dir / "presentation.pdf"
    if result.returncode != 0 or not pdf_path.is_file():
        diagnostic = (result.stderr or result.stdout or "no converter output").strip()
        raise PptxPreviewError(f"LibreOffice conversion failed: {diagnostic[-500:]}")
    return pdf_path


def _render_pdf_to_pngs(pdf_path: Path, output_dir: Path) -> list[Path]:
    try:
        import pymupdf
    except ImportError as error:  # pragma: no cover - dependency is required in deployments
        raise PptxPreviewError("PyMuPDF is not installed on the API server.") from error

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        document = pymupdf.open(pdf_path)
    except (OSError, RuntimeError, ValueError) as error:
        raise PptxPreviewError(f"Converted PDF could not be opened: {error}") from error

    paths: list[Path] = []
    try:
        if document.page_count == 0:
            raise PptxPreviewError("The converted presentation contains no slides.")
        page_limit = min(document.page_count, settings.pptx_preview_max_slides)
        for page_index in range(page_limit):
            page = document.load_page(page_index)
            scale = min(1280 / page.rect.width, 720 / page.rect.height)
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            output_path = output_dir / f"page_{page_index + 1:03d}.png"
            pixmap.save(output_path)
            paths.append(output_path)
    finally:
        document.close()
    return paths


def render_pptx_preview(pptx_path: Path) -> list[Path]:
    if not pptx_path.is_file():
        raise PptxPreviewError("The PPTX source file is unavailable.")

    cache_key = _file_sha256(pptx_path)
    cache_dir = _preview_cache_root() / cache_key
    cached_paths = _cached_slide_paths(cache_dir)
    if cached_paths:
        return cached_paths

    with _render_lock(cache_key):
        cached_paths = _cached_slide_paths(cache_dir)
        if cached_paths:
            return cached_paths

        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        staging_dir = cache_dir.parent / f".{cache_key}-{uuid.uuid4().hex}.tmp"
        staging_dir.mkdir()
        try:
            with tempfile.TemporaryDirectory(prefix="webagent-pptx-") as temporary_dir:
                pdf_path = _convert_pptx_to_pdf(pptx_path, Path(temporary_dir))
                rendered_paths = _render_pdf_to_pngs(pdf_path, staging_dir)
            if not rendered_paths:
                raise PptxPreviewError("No slide images were produced.")
            try:
                staging_dir.replace(cache_dir)
            except FileExistsError:
                shutil.rmtree(staging_dir, ignore_errors=True)
            return _cached_slide_paths(cache_dir)
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
