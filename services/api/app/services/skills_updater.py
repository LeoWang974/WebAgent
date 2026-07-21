import asyncio
import logging
import platform
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillsUpdateResult:
    cache_dir: str
    commit: str | None
    hermes_updated: bool = False
    openclaw_updated: bool = False
    source_dir: str | None = None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_skills_cache_dir() -> Path:
    return repo_root() / "runtime" / "sensenova-skills"


def default_openclaw_skills_dir() -> Path:
    return repo_root() / "runtime" / "openclaw-skills"


def _run_command(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        check=True,
        cwd=cwd,
        text=True,
        timeout=300,
    )


def _git_update(repo_url: str, cache_dir: Path, branch: str | None = None) -> str | None:
    cache_dir.parent.mkdir(parents=True, exist_ok=True)

    if (cache_dir / ".git").exists():
        _run_command(["git", "fetch", "--prune"], cwd=cache_dir)
        if branch:
            _run_command(["git", "checkout", branch], cwd=cache_dir)
            _run_command(["git", "pull", "--ff-only", "origin", branch], cwd=cache_dir)
        else:
            _run_command(["git", "pull", "--ff-only"], cwd=cache_dir)
    else:
        clone_args = ["git", "clone", "--depth", "1"]
        if branch:
            clone_args.extend(["--branch", branch])
        clone_args.extend([repo_url, str(cache_dir)])
        _run_command(clone_args)

    commit = _run_command(["git", "rev-parse", "HEAD"], cwd=cache_dir)
    return commit.stdout.strip() or None


def _windows_path_to_wsl(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix().split(":", maxsplit=1)[1].lstrip("/")
    return f"/mnt/{drive}/{rest}" if drive else resolved.as_posix()


def _is_wsl_absolute_path(path: str) -> bool:
    return path.startswith(("/home/", "/mnt/", "/opt/", "/usr/", "/var/"))


def _sync_local_directory(source_dir: Path, target_dir: Path) -> None:
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = target_dir.with_name(f"{target_dir.name}.tmp")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    shutil.copytree(source_dir, tmp_dir, ignore=shutil.ignore_patterns(".git"))
    if target_dir.exists():
        shutil.rmtree(target_dir)
    tmp_dir.replace(target_dir)


def _sync_wsl_directory(
    source_dir: Path,
    target_dir: str,
    *,
    wsl_distribution: str,
) -> None:
    source_wsl = _windows_path_to_wsl(source_dir)
    tmp_target = f"{target_dir}.tmp"
    command = (
        f"rm -rf {shlex.quote(tmp_target)} && "
        f"mkdir -p {shlex.quote(tmp_target)} && "
        f"cp -a {shlex.quote(source_wsl)}/. {shlex.quote(tmp_target)}/ && "
        f"rm -rf {shlex.quote(tmp_target)}/.git && "
        f"rm -rf {shlex.quote(target_dir)} && "
        f"mv {shlex.quote(tmp_target)} {shlex.quote(target_dir)}"
    )
    _run_command(
        [
            "wsl",
            "-d",
            wsl_distribution,
            "--",
            "bash",
            "-lc",
            command,
        ]
    )


def _sync_skills_target(
    source_dir: Path,
    target_dir: str | None,
    *,
    wsl_distribution: str,
) -> bool:
    if not target_dir:
        return False

    if platform.system().lower() == "windows" and _is_wsl_absolute_path(target_dir):
        _sync_wsl_directory(source_dir, target_dir, wsl_distribution=wsl_distribution)
    else:
        _sync_local_directory(source_dir, Path(target_dir).expanduser())
    return True


async def update_sensenova_skills(
    *,
    repo_url: str,
    cache_dir: str | None,
    source_subdir: str,
    branch: str | None,
    hermes_skills_dir: str | None,
    openclaw_skills_dir: str | None,
    wsl_distribution: str,
) -> SkillsUpdateResult:
    resolved_cache_dir = Path(cache_dir).expanduser() if cache_dir else default_skills_cache_dir()

    def run_update() -> SkillsUpdateResult:
        commit = _git_update(repo_url, resolved_cache_dir, branch)
        source_dir = (resolved_cache_dir / source_subdir).resolve()
        if not source_dir.exists() or not source_dir.is_dir():
            raise FileNotFoundError(f"SenseNova skills source directory not found: {source_dir}")

        hermes_updated = _sync_skills_target(
            source_dir,
            hermes_skills_dir,
            wsl_distribution=wsl_distribution,
        )
        openclaw_updated = _sync_skills_target(
            source_dir,
            openclaw_skills_dir,
            wsl_distribution=wsl_distribution,
        )
        return SkillsUpdateResult(
            cache_dir=str(resolved_cache_dir),
            commit=commit,
            hermes_updated=hermes_updated,
            openclaw_updated=openclaw_updated,
            source_dir=str(source_dir),
        )

    result = await asyncio.to_thread(run_update)
    logger.info("SenseNova skills update finished: %s", result)
    return result
