import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from app import schemas
from app.core.config import settings


def path_to_wsl(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if not drive:
        return resolved.as_posix()
    rest = resolved.as_posix().split(":", 1)[1].lstrip("/")
    return f"/mnt/{drive}/{rest}"


def run_pptx_export(
    deck_dir: Path,
    output_dir: Path,
    output_filename: str,
    timeout_seconds: int,
) -> Path | None:
    script_path = (
        f"{settings.hermes_home.rstrip('/')}"
        "/skills/sn-ppt-standard/scripts/export_pptx/html_to_pptx.mjs"
    )
    if os.name == "nt":
        command = (
            f"node {shlex.quote(script_path)} "
            f"--deck-dir {shlex.quote(path_to_wsl(deck_dir))} "
            f"--output {shlex.quote(output_filename)} "
            f"--output-dir {shlex.quote(path_to_wsl(output_dir))} "
            "--force"
        )
        result = subprocess.run(
            [
                "wsl",
                "-d",
                settings.hermes_wsl_distribution,
                "--",
                "bash",
                "-lc",
                command,
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    else:
        result = subprocess.run(
            [
                "node",
                script_path,
                "--deck-dir",
                str(deck_dir),
                "--output",
                output_filename,
                "--output-dir",
                str(output_dir),
                "--force",
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

    output_path = output_dir / output_filename
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path
    if result.returncode != 0:
        return None
    return None


def create_pptx_from_html_artifacts(
    session_id: str,
    html_artifacts: list[schemas.Artifact],
    run_id: str | None,
    timeout_seconds: int | None,
    *,
    artifact_from_path: Callable[..., schemas.Artifact | None],
    runtime_artifacts_dir: Callable[[str | None], Path],
    runtime_run_dir: Callable[[str | None], Path],
) -> schemas.Artifact | None:
    html_paths: list[Path] = []
    for artifact in html_artifacts:
        if artifact.type != "html_page":
            continue
        metadata = artifact.metadata or {}
        raw_path = str(metadata.get("path") or metadata.get("originalPath") or "")
        if not raw_path:
            continue
        path = Path(raw_path)
        if path.exists() and path.is_file():
            html_paths.append(path)

    if not html_paths:
        return None

    def sort_key(path: Path) -> tuple[int, str]:
        match = re.search(r"page[_-]?(\d+)", path.stem, re.IGNORECASE)
        return (int(match.group(1)) if match else 9999, path.name)

    html_paths = sorted(html_paths, key=sort_key)
    run_dir = runtime_run_dir(run_id)
    deck_dir = run_dir / "pptx-fallback"
    pages_dir = deck_dir / "pages"
    output_dir = runtime_artifacts_dir(run_id)
    pages_dir.mkdir(parents=True, exist_ok=True)

    for index, source in enumerate(html_paths, start=1):
        shutil.copy2(source, pages_dir / f"page_{index:03d}.html")

    output_filename = "agent-generated-deck.pptx"
    output_path = run_pptx_export(
        deck_dir,
        output_dir,
        output_filename,
        timeout_seconds or settings.agent_run_ppt_export_timeout_seconds,
    )
    if output_path is None:
        return None

    return artifact_from_path(
        session_id,
        output_path,
        original_path=str(output_path),
    )
