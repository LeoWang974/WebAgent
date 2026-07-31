import asyncio
import shlex
from collections.abc import Callable
from pathlib import Path


ARTIFACT_FIND_EXPR = (
    r"\( -iname '*.md' -o -iname '*.html' -o -iname '*.htm' "
    r"-o -iname '*.pptx' -o -iname '*.png' -o -iname '*.jpg' "
    r"-o -iname '*.jpeg' -o -iname '*.webp' -o -iname '*.csv' "
    r"-o -iname '*.xlsx' -o -iname '*.json' \)"
)


async def run_find_command(
    command: str,
    *,
    build_shell_args: Callable[[str], list[str]],
    timeout_seconds: int = 20,
) -> list[str]:
    process = await asyncio.create_subprocess_exec(
        *build_shell_args(command),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        return []
    return [
        line.strip()
        for line in stdout.decode("utf-8", errors="replace").splitlines()
        if line.strip()
    ]


def filter_report_artifacts(
    paths: list[str],
    *,
    skill_key: str | None = None,
    is_primary_output_artifact: Callable[[str], bool],
) -> list[str]:
    if skill_key == "ppt_generation":
        preferred = [
            path
            for path in paths
            if Path(path).suffix.lower() in {".ppt", ".pptx", ".html", ".htm"}
        ]
        if preferred:
            return preferred
    return [
        path
        for path in paths
        if Path(path).suffix.lower() == ".json" or is_primary_output_artifact(path)
    ]


async def find_report_artifacts(
    report_dirs: set[str],
    *,
    build_shell_args: Callable[[str], list[str]],
    is_primary_output_artifact: Callable[[str], bool],
) -> list[str]:
    if not report_dirs:
        return []
    quoted_dirs = " ".join(shlex.quote(path) for path in sorted(report_dirs))
    command = (
        f"for __dir in {quoted_dirs}; do "
        '[ -d "$__dir" ] || continue; '
        f'find "$__dir" -maxdepth 4 -type f {ARTIFACT_FIND_EXPR} -print; '
        "done"
    )
    paths = await run_find_command(command, build_shell_args=build_shell_args)
    return filter_report_artifacts(
        paths,
        is_primary_output_artifact=is_primary_output_artifact,
    )


async def find_recent_openclaw_artifacts(
    skill_key: str | None,
    *,
    build_shell_args: Callable[[str], list[str]],
    is_primary_output_artifact: Callable[[str], bool],
) -> list[str]:
    command = (
        'for __dir in "$HOME/.openclaw/workspace" "$HOME/.openclaw/artifacts"; do '
        '[ -d "$__dir" ] || continue; '
        f'find "$__dir" -maxdepth 6 -type f -mmin -240 {ARTIFACT_FIND_EXPR} -print; '
        "done"
    )
    paths = await run_find_command(command, build_shell_args=build_shell_args)
    return filter_report_artifacts(
        paths,
        skill_key=skill_key,
        is_primary_output_artifact=is_primary_output_artifact,
    )
