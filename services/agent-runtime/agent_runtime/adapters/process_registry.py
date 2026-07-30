import asyncio
import json
import os
import signal
from pathlib import Path

REGISTRY_ROOT = Path(__file__).resolve().parents[4] / "runtime" / "agent-processes"


def register_run_process(adapter: str, run_id: str | None, pid: int | None) -> None:
    if not run_id or not pid:
        return
    REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {"adapter": adapter, "run_id": run_id, "pid": pid, "pgid": _process_group_id(pid)}
    _registry_path(run_id).write_text(json.dumps(payload), encoding="utf-8")


def unregister_run_process(run_id: str | None, pid: int | None = None) -> None:
    if not run_id:
        return
    path = _registry_path(run_id)
    if not path.exists():
        return
    if pid is None:
        path.unlink(missing_ok=True)
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return
    if payload.get("pid") == pid:
        path.unlink(missing_ok=True)


async def terminate_registered_run_process(run_id: str) -> bool:
    pids, pgids = _registered_process_targets(run_id)
    killed = False
    for pgid in pgids:
        killed = await terminate_process_group(pgid) or killed
    for pid in pids:
        killed = await terminate_process_tree(pid) or killed
    marker_killed = await terminate_processes_by_marker(run_id)
    unregister_run_process(run_id)
    return killed or marker_killed


async def terminate_process_tree(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        process = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.communicate()
        return process.returncode == 0

    descendants = await _descendant_pids(pid)
    targets = list(dict.fromkeys([*descendants, pid]))
    if not targets:
        return False
    await _kill_posix(targets, signal="-TERM")
    await asyncio.sleep(2)
    await _kill_posix(targets, signal="-KILL")
    return True


async def terminate_process_group(pgid: int) -> bool:
    if os.name == "nt" or pgid <= 0:
        return False
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False
    await asyncio.sleep(2)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        pass
    return True


async def terminate_processes_by_marker(marker: str) -> bool:
    if not marker:
        return False
    if os.name == "nt":
        return False
    process = await asyncio.create_subprocess_exec(
        "pgrep",
        "-f",
        marker,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    pids = []
    current_pid = os.getpid()
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid != current_pid:
            pids.append(pid)
    if not pids:
        return False
    await _kill_posix(pids, signal="-TERM")
    await asyncio.sleep(2)
    await _kill_posix(pids, signal="-KILL")
    return True


def _registry_path(run_id: str) -> Path:
    safe_run_id = "".join(ch for ch in run_id if ch.isalnum() or ch in {"-", "_"})
    return REGISTRY_ROOT / f"{safe_run_id}.json"


def _process_group_id(pid: int) -> int | None:
    if os.name == "nt":
        return None
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return None
    return pgid if pgid == pid else None


def _registered_process_targets(run_id: str) -> tuple[list[int], list[int]]:
    path = _registry_path(run_id)
    if not path.exists():
        return [], []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return [], []
    pid = payload.get("pid")
    pgid = payload.get("pgid")
    pids = [pid] if isinstance(pid, int) else []
    pgids = [pgid] if isinstance(pgid, int) else []
    return pids, pgids


async def _descendant_pids(pid: int) -> list[int]:
    process = await asyncio.create_subprocess_exec(
        "ps",
        "-eo",
        "pid=,ppid=",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    children_by_parent: dict[int, list[int]] = {}
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            child_pid = int(parts[0])
            parent_pid = int(parts[1])
        except ValueError:
            continue
        children_by_parent.setdefault(parent_pid, []).append(child_pid)

    descendants: list[int] = []
    stack = list(children_by_parent.get(pid, []))
    while stack:
        child_pid = stack.pop()
        descendants.append(child_pid)
        stack.extend(children_by_parent.get(child_pid, []))
    descendants.reverse()
    return descendants


async def _kill_posix(pids: list[int], *, signal: str) -> None:
    if not pids:
        return
    process = await asyncio.create_subprocess_exec(
        "kill",
        signal,
        *(str(pid) for pid in pids),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.communicate()
