import asyncio
import json
import os
import re
import shlex
from collections.abc import AsyncGenerator
from pathlib import Path
from time import monotonic

from ..schemas import AgentArtifactRef, AgentRun, AgentRunCreate, AgentRunEvent, AgentRunStep
from .base import AgentRuntimeAdapter
from .openclaw_commands import (
    build_agent_cli_args,
    build_cli_args,
    build_openclaw_message,
    build_shell_args,
    with_runtime_env,
)
from .openclaw_artifact_finder import (
    find_recent_openclaw_artifacts,
    find_report_artifacts,
)
from .openclaw_protocol_events import protocol_events_from_tasks
from .openclaw_task_polling import poll_task_family_snapshot
from .openclaw_utils import (
    artifact_to_payload,
    clean_text_output,
    extract_output,
    extract_paths,
    extract_structured_artifacts,
    guess_artifact_type,
    is_openclaw_bootstrap_path,
    now_iso,
    safe_file_stem,
    source_dir_from_path,
    title_from_path,
)
from .process_registry import (
    register_run_process,
    terminate_registered_run_process,
    unregister_run_process,
)


class OpenClawAdapter(AgentRuntimeAdapter):
    """Adapter for OpenClaw's CLI/Gateway agent interface.

    The public adapter surface mirrors Hermes so WebAgent can switch runtimes
    through the same AgentRun/SSE pipeline. `gateway_cli` talks to a running
    OpenClaw Gateway through the CLI; `local_cli` keeps the previous embedded
    fallback for machines without a Gateway process.
    """

    def __init__(
        self,
        base_url: str = "ws://127.0.0.1:18789",
        *,
        agent_id: str = "main",
        cli_path: str = "openclaw",
        command_timeout_seconds: int = 600,
        mode: str = "gateway_cli",
        home_dir: str | None = None,
        skills_dir: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.cli_path = cli_path
        self.command_timeout_seconds = command_timeout_seconds
        self.mode = mode
        self.home_dir = home_dir
        self.skills_dir = skills_dir
        self.active_processes: dict[str, asyncio.subprocess.Process] = {}
        self.cancelled_run_ids: set[str] = set()
        self.run_task_ids: dict[str, set[str]] = {}
        self.last_artifact_paths: list[str] = []
        self.last_artifacts: list[AgentArtifactRef] = []
        self.last_diagnostics: dict[str, object] = {}

    async def create_run(self, input_data: AgentRunCreate) -> AgentRun:
        output = None
        error = None
        status = "completed"
        try:
            events = [event async for event in self.stream_response_events(input_data)]
            output = next((event.output for event in reversed(events) if event.output), None)
            if not output and events:
                output = events[-1].step.label if events[-1].step else None
        except Exception as exc:
            status = "failed"
            error = str(exc)

        return AgentRun(
            id=input_data.run_id or f"run_openclaw_{input_data.session_id}",
            session_id=input_data.session_id,
            status=status,
            title="OpenClaw Agent Run",
            progress=100 if status == "completed" else 0,
            steps=[],
            started_at=now_iso(),
            completed_at=now_iso() if status == "completed" else None,
            error=error,
            output=output,
            artifacts=self.get_last_artifacts(),
        )

    async def get_run(self, run_id: str) -> AgentRun:
        return AgentRun(
            id=run_id,
            session_id="",
            status="cancelled" if run_id in self.cancelled_run_ids else "completed",
            title="OpenClaw Agent Run",
            progress=100,
            steps=[],
            started_at=now_iso(),
            completed_at=now_iso(),
        )

    async def cancel_run(self, run_id: str) -> AgentRun:
        self.cancelled_run_ids.add(run_id)
        process = self.active_processes.get(run_id)
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()
        await terminate_registered_run_process(run_id)
        await self._cancel_openclaw_tasks(run_id)
        return AgentRun(
            id=run_id,
            session_id="",
            status="cancelled",
            title="OpenClaw Agent Run",
            progress=0,
            steps=[],
            started_at=now_iso(),
            completed_at=now_iso(),
        )

    async def stream_events(self, run_id: str) -> AsyncGenerator[AgentRunEvent, None]:
        yield AgentRunEvent(
            run_id=run_id,
            event_type="stage_started",
            status="running",
            progress=10,
            step=AgentRunStep(
                id=f"{run_id}_openclaw_waiting",
                label="Waiting for OpenClaw agent output",
                status="running",
                timestamp=now_iso(),
            ),
        )

    async def stream_response(self, input_data: AgentRunCreate) -> AsyncGenerator[str, None]:
        async for event in self.stream_response_events(input_data):
            if event.output:
                yield event.output
            elif event.step and event.step.label:
                yield event.step.label

    async def stream_response_events(
        self,
        input_data: AgentRunCreate,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        run_id = input_data.run_id or input_data.session_id
        self._reset_last_state()
        final_artifact_found = False
        should_track_background = self._should_track_task_family(input_data)
        artifact_filter_key = self._artifact_filter_key(input_data)
        poll_state = self._new_poll_state()
        report_dirs = self._extract_report_dirs(input_data.content)
        report_dirs.update(self._extract_file_parent_dirs(input_data.content))
        forced_fallback_completion = False

        if should_track_background:
            yield self._stage_event(
                run_id,
                "stage_started",
                "OpenClaw agent started.",
                10,
            )

        process = await self._start_agent_process(input_data, run_id)
        cli_timed_out = False
        stdout = b""
        stderr = b""
        communicate_task = asyncio.create_task(process.communicate())
        try:
            if should_track_background:
                started_at = monotonic()
                while True:
                    try:
                        stdout, stderr = await asyncio.wait_for(
                            asyncio.shield(communicate_task),
                            timeout=self._foreground_poll_interval_seconds(artifact_filter_key),
                        )
                        break
                    except TimeoutError:
                        elapsed = monotonic() - started_at
                        if elapsed >= self.command_timeout_seconds:
                            cli_timed_out = True
                            stdout, stderr = await self._kill_and_collect_output(
                                process,
                                communicate_task,
                            )
                            self.last_diagnostics = {
                                "adapter": "openclaw",
                                "mode": self.mode,
                                "timeoutSeconds": self.command_timeout_seconds,
                                "cliTimedOut": True,
                            }
                            break

                        events = await self._poll_task_family_snapshot(
                            input_data,
                            run_id,
                            report_dirs,
                            poll_state,
                        )
                        for event in events:
                            yield event
                        if self._primary_output_artifact_paths(artifact_filter_key):
                            final_artifact_found = True
                            stdout, stderr = await self._kill_and_collect_output(
                                process,
                                communicate_task,
                            )
                            break
                        if (
                            artifact_filter_key in {"html_generation", "ppt_generation"}
                            and elapsed >= self._no_task_family_timeout_seconds(artifact_filter_key)
                            and int(self.last_diagnostics.get("matchingTaskCount", 0) or 0) == 0
                            and not self.last_artifact_paths
                        ):
                            forced_fallback_completion = True
                            stdout, stderr = await self._kill_and_collect_output(
                                process,
                                communicate_task,
                            )
                            output = (
                                "OpenClaw did not emit a task family or final artifact in time; "
                                "WebAgent will discover or synthesize the requested artifact."
                            )
                            stdout = output.encode("utf-8")
                            break
                        if (
                            artifact_filter_key in {"html_generation", "ppt_generation"}
                            and elapsed >= self._no_artifact_timeout_seconds(artifact_filter_key)
                            and not self._primary_output_artifact_paths(artifact_filter_key)
                        ):
                            forced_fallback_completion = True
                            stdout, stderr = await self._kill_and_collect_output(
                                process,
                                communicate_task,
                            )
                            output = (
                                "OpenClaw did not produce a final artifact in time; "
                                "WebAgent will discover or synthesize the requested artifact."
                            )
                            stdout = output.encode("utf-8")
                            break
            else:
                stdout, stderr = await asyncio.wait_for(
                    communicate_task,
                    timeout=self.command_timeout_seconds,
                )
        except TimeoutError as exc:
            cli_timed_out = True
            if should_track_background:
                stdout, stderr = await self._kill_and_collect_output(
                    process,
                    communicate_task,
                )
            else:
                await self.cancel_run(run_id)
                self.last_diagnostics = {
                    "adapter": "openclaw",
                    "mode": self.mode,
                    "timeoutSeconds": self.command_timeout_seconds,
                }
                raise RuntimeError("OpenClaw agent command timed out.") from exc
            self.last_diagnostics = {
                "adapter": "openclaw",
                "mode": self.mode,
                "timeoutSeconds": self.command_timeout_seconds,
                "cliTimedOut": True,
            }
        finally:
            self.active_processes.pop(run_id, None)
            unregister_run_process(run_id, getattr(process, "pid", None))

        raw_stdout = stdout.decode("utf-8", errors="replace")
        raw_stderr = stderr.decode("utf-8", errors="replace")
        self._remember_artifact_paths(raw_stdout)
        self._remember_artifact_paths(raw_stderr)
        output = extract_output(raw_stdout, raw_stderr)
        structured_artifacts = extract_structured_artifacts(
            raw_stdout,
            raw_stderr,
        )
        for artifact in structured_artifacts:
            artifact.run_id = artifact.run_id or run_id
            self._remember_artifact_ref(artifact)
        for artifact in self.last_artifacts:
            artifact.run_id = artifact.run_id or run_id

        if (
            not final_artifact_found
            and not forced_fallback_completion
            and (cli_timed_out or self._should_wait_for_background_completion(input_data, output))
        ):
            async for event in self._poll_background_completion(
                input_data,
                run_id,
                output or input_data.content,
                report_dirs,
                poll_state,
            ):
                yield event
            final_artifact_found = bool(self._primary_output_artifact_paths(artifact_filter_key))

        if not self.last_artifacts:
            self._create_fallback_artifact_from_output(input_data, run_id, output)
        self.last_diagnostics = {
            "adapter": "openclaw",
            "mode": self.mode,
            "exitCode": process.returncode,
            "stderrTail": raw_stderr[-2000:],
            "stdoutTail": raw_stdout[-2000:],
            "artifactPaths": list(self.last_artifact_paths),
            "artifactCount": len(self.last_artifact_paths),
            "cliTimedOut": cli_timed_out,
            "finalArtifactFound": final_artifact_found,
            "reportDirs": sorted(report_dirs),
            "artifactFilterKey": artifact_filter_key,
            "trackedBackground": should_track_background,
        }

        if (
            process.returncode != 0
            and not cli_timed_out
            and not final_artifact_found
            and not forced_fallback_completion
        ):
            raise RuntimeError(
                f"OpenClaw exited with code {process.returncode}: "
                f"{(raw_stderr or raw_stdout).strip()[-1000:]}"
            )

        for index, artifact in enumerate(self.last_artifacts, start=1):
            yield AgentRunEvent(
                run_id=run_id,
                event_type="artifact_found",
                status="running",
                progress=90,
                payload={
                    "protocol": "openclaw.cli.v1",
                    "mode": self.mode,
                    "artifact_paths": list(self.last_artifact_paths),
                    "artifact": artifact_to_payload(artifact),
                },
                step=AgentRunStep(
                    id=f"{run_id}_openclaw_artifact_{index}",
                    label=f"OpenClaw artifact found: {artifact.path}",
                    status="completed",
                    timestamp=now_iso(),
                ),
            )

        yield AgentRunEvent(
            run_id=run_id,
            event_type="completed",
            status="completed",
            progress=100,
            completed_at=now_iso(),
            output=output,
            payload={
                "protocol": "openclaw.cli.v1",
                "mode": self.mode,
                "artifact_paths": list(self.last_artifact_paths),
                "artifacts": [artifact_to_payload(item) for item in self.last_artifacts],
            },
            step=AgentRunStep(
                id=f"{run_id}_openclaw_completed",
                label=output or "OpenClaw completed without visible output.",
                status="completed",
                timestamp=now_iso(),
            ),
        )

    def get_last_artifact_paths(self) -> list[str]:
        return list(self.last_artifact_paths)

    def get_last_artifacts(self) -> list[AgentArtifactRef]:
        return list(self.last_artifacts)

    def get_last_diagnostics(self) -> dict[str, object]:
        return dict(self.last_diagnostics)

    async def health_check(self) -> dict[str, object]:
        process = await asyncio.create_subprocess_exec(
            *self._build_cli_args(["health", "--json", "--timeout", "3000"]),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        raw_stdout = stdout.decode("utf-8", errors="replace").strip()
        raw_stderr = stderr.decode("utf-8", errors="replace").strip()
        return {
            "ok": process.returncode == 0,
            "exitCode": process.returncode,
            "stdout": raw_stdout,
            "stderr": raw_stderr,
        }

    async def _start_agent_process(
        self,
        input_data: AgentRunCreate,
        run_id: str,
    ) -> asyncio.subprocess.Process:
        process = await asyncio.create_subprocess_exec(
            *self._build_agent_cli_args(input_data),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **({"start_new_session": True} if os.name != "nt" else {}),
        )
        self.active_processes[run_id] = process
        register_run_process("openclaw", run_id, process.pid)
        return process

    @staticmethod
    async def _kill_and_collect_output(
        process: asyncio.subprocess.Process,
        communicate_task: asyncio.Task,
    ) -> tuple[bytes, bytes]:
        if process.returncode is None:
            process.kill()
        try:
            return await asyncio.wait_for(asyncio.shield(communicate_task), timeout=5)
        except TimeoutError:
            if communicate_task.done():
                try:
                    return await asyncio.wait_for(process.communicate(), timeout=5)
                except (TimeoutError, asyncio.CancelledError):
                    return b"", b"OpenClaw process did not terminate promptly after kill."
            if not communicate_task.done():
                communicate_task.cancel()
            return b"", b"OpenClaw process did not terminate promptly after kill."
        except asyncio.CancelledError:
            if not communicate_task.done():
                communicate_task.cancel()
            return b"", b"OpenClaw process did not terminate promptly after kill."

    def _build_agent_cli_args(self, input_data: AgentRunCreate) -> list[str]:
        return build_agent_cli_args(
            input_data,
            agent_id=self.agent_id,
            cli_path=self.cli_path,
            command_timeout_seconds=self.command_timeout_seconds,
            mode=self.mode,
            runtime_env=self._runtime_env(),
        )

    def _build_openclaw_message(self, input_data: AgentRunCreate) -> str:
        return build_openclaw_message(input_data)

    def _build_local_cli_args(self, input_data: AgentRunCreate) -> list[str]:
        previous_mode = self.mode
        self.mode = "local_cli"
        try:
            return self._build_agent_cli_args(input_data)
        finally:
            self.mode = previous_mode

    def _build_cli_args(self, args: list[str]) -> list[str]:
        return build_cli_args(args, cli_path=self.cli_path, runtime_env=self._runtime_env())

    def _build_shell_args(self, command: str) -> list[str]:
        return build_shell_args(command, self._runtime_env())

    @staticmethod
    def _with_runtime_env(command: str, extra_env: dict[str, str | None] | None = None) -> str:
        return with_runtime_env(command, extra_env)

    def _runtime_env(self) -> dict[str, str | None]:
        return {
            "HOME": self.home_dir,
            "OPENCLAW_HOME": self.home_dir,
            "OPENCLAW_SKILLS_DIR": self.skills_dir,
        }

    def _reset_last_state(self) -> None:
        self.last_artifact_paths = []
        self.last_artifacts = []
        self.last_diagnostics = {}

    def _remember_artifact_paths(self, text: str) -> None:
        for path in extract_paths(text):
            self._remember_artifact_path(path)

    def _remember_artifact_path(self, path: str) -> None:
        self._remember_artifact_ref(AgentArtifactRef(path=path))

    def _remember_artifact_ref(self, artifact: AgentArtifactRef) -> None:
        path = artifact.path
        if is_openclaw_bootstrap_path(path):
            return
        existing_index = next(
            (index for index, item in enumerate(self.last_artifacts) if item.path == path),
            None,
        )
        if existing_index is not None:
            existing = self.last_artifacts[existing_index]
            existing.artifact_type = artifact.artifact_type or existing.artifact_type
            existing.source_dir = artifact.source_dir or existing.source_dir
            existing.run_id = artifact.run_id or existing.run_id
            existing.title = artifact.title or existing.title
            return
        self.last_artifact_paths.append(path)
        self.last_artifacts.append(
            AgentArtifactRef(
                path=path,
                artifact_type=artifact.artifact_type or guess_artifact_type(path),
                run_id=artifact.run_id,
                source_dir=artifact.source_dir or source_dir_from_path(path),
                title=artifact.title or title_from_path(path),
            )
        )

    async def _run_openclaw_json_command(
        self,
        args: list[str],
        timeout_seconds: int = 20,
    ) -> dict[str, object] | None:
        process = await asyncio.create_subprocess_exec(
            *self._build_cli_args(args),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                return None
            return None

        text = self._first_json_like_text(stdout, stderr)
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    async def _run_openclaw_command(
        self,
        args: list[str],
        timeout_seconds: int = 20,
    ) -> tuple[int | None, str, str]:
        process = await asyncio.create_subprocess_exec(
            *self._build_cli_args(args),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                return None, "", "OpenClaw command did not terminate promptly after kill."
            return None, "", "OpenClaw command timed out."
        return (
            process.returncode,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    async def _cancel_openclaw_tasks(self, run_id: str) -> None:
        task_ids = set(self.run_task_ids.pop(run_id, set()))
        tasks_payload = await self._run_openclaw_json_command(
            ["tasks", "list", "--json"],
            timeout_seconds=20,
        )
        raw_tasks = []
        if isinstance(tasks_payload, dict):
            raw = tasks_payload.get("tasks")
            raw_tasks = raw if isinstance(raw, list) else []
        for task in raw_tasks:
            if not isinstance(task, dict):
                continue
            task_text = self._task_text(task)
            if f"webagent_run_id={run_id}" not in task_text:
                continue
            task_id = task.get("taskId")
            if isinstance(task_id, str) and task.get("status") in {"queued", "running"}:
                task_ids.add(task_id)
        for task_id in sorted(task_ids):
            await self._run_openclaw_command(
                ["tasks", "cancel", task_id],
                timeout_seconds=20,
            )

    @staticmethod
    def _first_json_like_text(*chunks: bytes) -> str:
        for chunk in chunks:
            text = chunk.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            json_start = min(
                (index for index in (text.find("{"), text.find("[")) if index >= 0),
                default=-1,
            )
            if json_start >= 0:
                return text[json_start:]
        return ""

    async def _find_report_artifacts(self, report_dirs: set[str]) -> list[str]:
        return await find_report_artifacts(
            report_dirs,
            build_shell_args=self._build_shell_args,
            is_primary_output_artifact=self._is_primary_output_artifact,
        )

    async def _find_recent_openclaw_artifacts(
        self,
        skill_key: str | None,
        input_data: AgentRunCreate | None = None,
    ) -> list[str]:
        paths = await find_recent_openclaw_artifacts(
            skill_key,
            build_shell_args=self._build_shell_args,
            is_primary_output_artifact=self._is_primary_output_artifact,
        )
        return [
            path
            for path in paths
            if self._recent_artifact_matches_input(path, skill_key, input_data)
        ]

    async def _discover_report_dirs_from_input(self, input_data: AgentRunCreate) -> set[str]:
        needles = self._report_dir_search_needles(input_data.content)
        if not needles:
            return set()
        script = r"""
import json
import os
from pathlib import Path

needles = json.loads(os.environ.get("WEBAGENT_OPENCLAW_NEEDLES", "[]"))
root = Path.home() / ".openclaw" / "workspace" / "deep-research-reports"
matches = []
if root.exists():
    for child in root.iterdir():
        if not child.is_dir():
            continue
        haystacks = [child.name]
        for name in ("request.md", "plan.json", "synthesis.md", "report.md"):
            path = child / name
            if path.exists():
                try:
                    haystacks.append(path.read_text(encoding="utf-8", errors="ignore")[:20000])
                except OSError:
                    pass
        haystack = "\n".join(haystacks).lower()
        if any(needle.lower() in haystack for needle in needles):
            matches.append(str(child))
for item in sorted(matches):
    print(item)
"""
        env_value = json.dumps(needles, ensure_ascii=False)
        command = (
            f"WEBAGENT_OPENCLAW_NEEDLES={shlex.quote(env_value)} "
            f"python3 -c {shlex.quote(script)}"
        )
        process = await asyncio.create_subprocess_exec(
            *self._build_shell_args(command),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=20)
        except TimeoutError:
            process.kill()
            await process.wait()
            return set()
        return {
            line.strip()
            for line in stdout.decode("utf-8", errors="replace").splitlines()
            if line.strip()
        }

    @staticmethod
    def _report_dir_search_needles(content: str) -> list[str]:
        needles: list[str] = []
        for match in re.finditer(r"《([^》]{2,120})》", content):
            needles.append(match.group(1).strip())
        user_request_match = re.search(
            r"\[User request\]\s*(.+?)(?:\n\s*\[|$)",
            content,
            re.DOTALL,
        )
        if user_request_match:
            request = re.sub(r"\s+", " ", user_request_match.group(1)).strip()
            if request:
                needles.append(request[:120])
        cleaned = re.sub(r"\s+", " ", content).strip()
        if cleaned:
            needles.append(cleaned[:120])
        seen: set[str] = set()
        unique: list[str] = []
        for needle in needles:
            if needle and needle not in seen:
                seen.add(needle)
                unique.append(needle)
        return unique

    @classmethod
    def _recent_artifact_matches_input(
        cls,
        path: str,
        skill_key: str | None,
        input_data: AgentRunCreate | None,
    ) -> bool:
        if skill_key not in {"ppt_generation", "html_generation"}:
            return True
        if input_data is None:
            return False
        needles = [
            cls._artifact_match_key(needle)
            for needle in cls._report_dir_search_needles(input_data.content)
        ]
        needles = [needle for needle in needles if len(needle) >= 6]
        if not needles:
            return False
        haystack = cls._artifact_match_key(path)
        return any(needle in haystack for needle in needles)

    @staticmethod
    def _artifact_match_key(value: str) -> str:
        return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).lower()

    @staticmethod
    def _extract_report_dirs(text: str) -> set[str]:
        pattern = re.compile(
            r"(?P<path>(?:[A-Za-z]:\\|/mnt/[a-z]/|/)[^\s'\"<>`]*"
            r"deep-research-reports[^\s'\"<>`]*)",
            re.IGNORECASE,
        )
        dirs: set[str] = set()
        for match in pattern.finditer(text):
            raw_path = match.group("path").rstrip(".,;:)`")
            suffix = Path(raw_path).suffix.lower()
            if suffix:
                dirs.add(str(Path(raw_path).parent))
            else:
                dirs.add(raw_path)
        return dirs

    @staticmethod
    def _normalize_shell_path(path: str) -> str:
        value = path.strip().strip(".,;:)`\"'")
        match = re.match(r"^([A-Za-z]):[\\/](.*)$", value)
        if match:
            drive = match.group(1).lower()
            rest = match.group(2).replace("\\", "/")
            return f"/mnt/{drive}/{rest}"
        return value.replace("\\", "/")

    @classmethod
    def _extract_file_parent_dirs(cls, text: str) -> set[str]:
        dirs: set[str] = set()
        for path in extract_paths(text):
            normalized = cls._normalize_shell_path(path)
            if Path(normalized).suffix and "/" in normalized:
                dirs.add(normalized.rsplit("/", maxsplit=1)[0])
        return dirs

    @staticmethod
    def _task_text(task: dict[str, object]) -> str:
        return OpenClawAdapter._repair_mojibake(
            json.dumps(task, ensure_ascii=False),
        )

    @staticmethod
    def _repair_mojibake(text: str) -> str:
        original_chinese_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        best = text
        best_chinese_count = original_chinese_count
        for encoding in ("latin1", "cp1252"):
            try:
                candidate = text.encode(encoding).decode("utf-8")
            except UnicodeError:
                continue
            chinese_count = sum(1 for char in candidate if "\u4e00" <= char <= "\u9fff")
            if chinese_count > best_chinese_count:
                best = candidate
                best_chinese_count = chinese_count
        return best

    @staticmethod
    def _task_family_keys(tasks: list[dict[str, object]]) -> set[str]:
        keys: set[str] = set()
        generic_keys = {"agent:main:main", "main", ""}
        for task in tasks:
            for key in (
                "taskId",
                "sourceId",
                "runId",
                "parentFlowId",
                "childSessionKey",
                "requesterSessionKey",
            ):
                value = task.get(key)
                if isinstance(value, str) and value not in generic_keys:
                    keys.add(value)
        return keys

    def _matching_task_family(
        self,
        tasks: list[dict[str, object]],
        input_data: AgentRunCreate,
        report_dirs: set[str],
    ) -> list[dict[str, object]]:
        seed_tasks = [
            task
            for task in tasks
            if self._task_matches_input(task, input_data, report_dirs)
        ]
        if not seed_tasks:
            return []

        family_keys = self._task_family_keys(seed_tasks)
        family_tasks = list(seed_tasks)
        previous_count = -1
        while previous_count != len(family_tasks):
            previous_count = len(family_tasks)
            for task in family_tasks:
                task_text = self._task_text(task)
                report_dirs.update(self._extract_report_dirs(task_text))
                report_dirs.update(self._extract_file_parent_dirs(task_text))
            for task in tasks:
                if task in family_tasks:
                    continue
                task_text = self._task_text(task)
                has_report_dir = any(report_dir in task_text for report_dir in report_dirs)
                shares_family_key = any(key and key in task_text for key in family_keys)
                if has_report_dir or shares_family_key:
                    family_tasks.append(task)
                    family_keys.update(self._task_family_keys([task]))
        return family_tasks

    @staticmethod
    def _is_primary_output_artifact(path: str) -> bool:
        normalized_path = path.replace("\\", "/").lower()
        name = Path(path).name.lower()
        suffix = Path(path).suffix.lower()
        if suffix == ".json" or name in {"briefing.json", "plan.json", "blueprint.json"}:
            return False
        if name in {"request.md", "synthesis.md", "outline.md"}:
            return False
        if "/sub_reports/" in normalized_path or "subreport" in name:
            return False
        return suffix in {
            ".md",
            ".markdown",
            ".html",
            ".htm",
            ".pptx",
            ".ppt",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".csv",
            ".xlsx",
        }

    @staticmethod
    def _should_wait_for_background_completion(
        input_data: AgentRunCreate,
        output: str,
    ) -> bool:
        if not OpenClawAdapter._should_track_task_family(input_data):
            return False
        normalized = output.lower()
        start_markers = [
            "start",
            "started",
            "begin",
            "\u5f00\u59cb",
            "\u542f\u52a8",
            "\u7b2c\u4e00\u6b65",
            "scout",
            "briefing",
            "\u9884\u68c0",
        ]
        final_markers = [
            "\u62a5\u544a\u5df2\u751f\u6210",
            "\u62a5\u544a\u5df2\u5b8c\u6210",
            "artifact_paths",
            ".md",
            ".pptx",
        ]
        return any(marker in normalized for marker in start_markers) and not any(
            marker in normalized for marker in final_markers
        )

    @staticmethod
    def _artifact_filter_key(input_data: AgentRunCreate) -> str | None:
        if input_data.skill_key:
            return input_data.skill_key
        normalized = input_data.content.lower()
        action_markers = (
            "output",
            "generate",
            "create",
            "write",
            "export",
            "research",
            "调研",
            "输出",
            "生成",
            "创建",
            "撰写",
            "导出",
        )
        has_action = any(marker in normalized for marker in action_markers)
        has_cjk = any("\u4e00" <= char <= "\u9fff" for char in input_data.content)
        if any(marker in normalized for marker in (".pptx", "ppt", "slides", "slide deck", "幻灯片")):
            return "ppt_generation"
        if has_action and any(marker in normalized for marker in (".html", " html", "网页", "页面")):
            return "html_generation"
        if has_action and any(marker in normalized for marker in ("image", "png", "jpg", "jpeg", "webp", "图片", "生图")):
            return "u1_image"
        if has_action and any(
            marker in normalized
            for marker in (
                ".md",
                "markdown",
                "report",
                "research",
                "调研",
                "报告",
                "分析",
            )
        ):
            return "deep_research"
        if has_action and has_cjk and ("《" in input_data.content and "》" in input_data.content):
            return "deep_research"
        return None

    @staticmethod
    def _should_track_task_family(input_data: AgentRunCreate) -> bool:
        return OpenClawAdapter._artifact_filter_key(input_data) is not None

    @staticmethod
    def _summarize_task_label(
        task: dict[str, object],
        skill_key: str | None = None,
        *,
        user_content: str = "",
    ) -> str:
        task_text = OpenClawAdapter._repair_mojibake(str(task.get("task") or ""))
        status = str(task.get("status") or "running")
        field_label = OpenClawAdapter._task_field_label(task)
        if field_label:
            return field_label
        dimension_match = re.search(r"dimension_id\s*:\s*([A-Za-z0-9_-]+)", task_text)
        dimension_name_match = re.search(
            r"(?:维度名称|dimension_name|dimension)\s*[:：]\s*([^\n\r]+)",
            task_text,
        )
        result_match = re.search(
            r"<<<BEGIN_UNTRUSTED_CHILD_RESULT>>>\s*(.*?)\s*<<<END_UNTRUSTED_CHILD_RESULT>>>",
            task_text,
            re.DOTALL,
        )
        dimension = dimension_match.group(1) if dimension_match else ""
        dimension_name = (
            OpenClawAdapter._compact_label(dimension_name_match.group(1), max_chars=80)
            if dimension_name_match
            else ""
        )
        result = (
            OpenClawAdapter._compact_label(result_match.group(1), max_chars=140)
            if result_match
            else ""
        )
        if dimension:
            if status in {"queued", "running"}:
                if "status: timed out" in task_text.lower():
                    return f"OpenClaw is retrying or repairing evidence for {dimension}."
                if dimension_name:
                    return f"OpenClaw is researching {dimension}: {dimension_name}"
                return f"OpenClaw is researching {dimension}."
            if status == "succeeded":
                if result:
                    return f"OpenClaw completed {dimension}: {result}"
                if dimension_name:
                    return f"OpenClaw completed {dimension}: {dimension_name}"
                return f"OpenClaw completed {dimension}."

        for key in ("progressSummary", "label"):
            value = task.get(key)
            if isinstance(value, str) and value.strip():
                return OpenClawAdapter._compact_label(OpenClawAdapter._repair_mojibake(value))

        runtime = str(task.get("runtime") or "task")
        if skill_key == "ppt_generation" and status in {"queued", "running"}:
            return "OpenClaw is generating slides and watching for PPT/HTML artifacts."
        if skill_key == "html_generation" and status in {"queued", "running"}:
            source_match = re.search(
                r"path=([^\s]+(?:\.md|\.markdown))",
                task_text,
                re.IGNORECASE,
            )
            source_name = Path(source_match.group(1)).name if source_match else "source report"
            return f"OpenClaw is generating an HTML report from {source_name}."
        if skill_key == "deep_research" and status in {"queued", "running"}:
            title_match = re.search(r"《([^》]+)》", task_text) or re.search(
                r"《([^》]+)》",
                user_content,
            )
            title = f"《{title_match.group(1)}》" if title_match else "the research topic"
            return f"OpenClaw 正在调研 {title}，等待阶段输出或 Markdown 产物。"
        fallback_label = OpenClawAdapter._summarize_user_request_label(user_content, skill_key)
        if fallback_label:
            return fallback_label
        if status == "succeeded":
            return f"OpenClaw {runtime} task completed; waiting for child tasks or artifacts."
        useful_lines = [
            line.strip(" -")
            for line in task_text.splitlines()
            if line.strip()
            and "webagent_run_id=" not in line
            and "webagent_skill=" not in line
            and not line.strip().startswith("[")
        ]
        if useful_lines:
            return (
                "OpenClaw is working on: "
                f"{OpenClawAdapter._compact_label(useful_lines[0], max_chars=220)}"
            )
        return f"OpenClaw {runtime} task status: {status}."

    @staticmethod
    def _task_field_label(task: dict[str, object]) -> str:
        for key in (
            "progressSummary",
            "progress_summary",
            "label",
            "title",
            "name",
            "summary",
            "message",
            "lastMessage",
            "last_message",
            "lastOutput",
            "last_output",
            "output",
        ):
            value = task.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            repaired = OpenClawAdapter._repair_mojibake(value)
            cleaned = OpenClawAdapter._compact_label(repaired, max_chars=220)
            if OpenClawAdapter._is_low_value_task_label(cleaned):
                continue
            return cleaned
        return ""

    @staticmethod
    def _is_low_value_task_label(label: str) -> bool:
        normalized = label.lower().strip()
        if not normalized:
            return True
        low_value_markers = {
            "running",
            "queued",
            "succeeded",
            "completed",
            "openclaw cli task is running.",
            "openclaw cli task status: running.",
            "openclaw is still working; waiting for task progress.",
        }
        return normalized in low_value_markers or "webagent_run_id=" in normalized

    @staticmethod
    def _summarize_user_request_label(
        content: str,
        skill_key: str | None = None,
        *,
        suffix: str = "",
    ) -> str:
        title_match = re.search(r"《([^》]{2,120})》", content)
        title = f"《{title_match.group(1)}》" if title_match else ""
        if skill_key == "ppt_generation":
            base = f"OpenClaw 正在生成 {title or 'PPT'}"
        elif skill_key == "html_generation":
            base = f"OpenClaw 正在生成 {title or 'HTML 页面'}"
        elif skill_key == "deep_research":
            base = f"OpenClaw 正在调研 {title or '当前主题'}"
        elif skill_key == "u1_image":
            base = f"OpenClaw 正在生成 {title or '图片'}"
        elif skill_key:
            base = f"OpenClaw 正在处理 {title or '当前任务'}"
        else:
            return ""
        return f"{base}，{suffix}" if suffix else f"{base}，等待阶段输出或最终产物。"

    @staticmethod
    def _compact_label(value: str, max_chars: int = 360) -> str:
        cleaned = clean_text_output(value)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[: max_chars - 1].rstrip() + "\u2026"

    def _task_matches_input(
        self,
        task: dict[str, object],
        input_data: AgentRunCreate,
        report_dirs: set[str],
    ) -> bool:
        task_text = self._task_text(task)
        if input_data.run_id:
            run_marker = f"webagent_run_id={input_data.run_id}"
            if run_marker in task_text:
                return True
            if "webagent_run_id=" in task_text:
                return False
        if input_data.content and input_data.content[:40] in task_text:
            return True
        for needle in self._report_dir_search_needles(input_data.content):
            if needle in task_text:
                return True
        return any(report_dir in task_text for report_dir in report_dirs)

    @staticmethod
    def _new_poll_state() -> dict[str, object]:
        return {
            "last_label": "",
            "last_artifact_count": 0,
            "last_visible_emit_at": 0.0,
            "progress": 20,
            "recoverable_failure_reported": False,
        }

    @staticmethod
    def _foreground_poll_interval_seconds(skill_key: str | None) -> int:
        if skill_key in {"deep_research", "ppt_generation", "html_generation"}:
            return 10
        return 6

    def _primary_output_artifact_paths(self, skill_key: str | None = None) -> list[str]:
        primary_paths: list[str] = []
        for path in self.last_artifact_paths:
            if not self._is_primary_output_artifact(path):
                continue
            suffix = Path(path).suffix.lower()
            if skill_key == "ppt_generation" and suffix not in {".ppt", ".pptx"}:
                continue
            if skill_key == "html_generation" and suffix not in {".html", ".htm"}:
                continue
            if skill_key == "u1_image" and suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            primary_paths.append(path)
        return primary_paths

    def _remember_structured_artifacts_from_value(
        self,
        value: object,
        run_id: str,
    ) -> None:
        artifacts = extract_structured_artifacts(
            json.dumps(value, ensure_ascii=False),
            "",
        )
        for artifact in artifacts:
            artifact.run_id = artifact.run_id or run_id
            self._remember_artifact_ref(artifact)

    def _protocol_events_from_tasks(
        self,
        run_id: str,
        tasks: list[dict[str, object]],
        poll_state: dict[str, object],
    ) -> list[AgentRunEvent]:
        events = protocol_events_from_tasks(
            run_id,
            tasks,
            poll_state,
            compact_label=self._compact_label,
            remember_artifact_ref=self._remember_artifact_ref,
        )
        for event in events:
            event.payload = {**(event.payload or {}), "mode": self.mode}
        return events

    async def _poll_task_family_snapshot(
        self,
        input_data: AgentRunCreate,
        run_id: str,
        report_dirs: set[str],
        poll_state: dict[str, object],
    ) -> list[AgentRunEvent]:
        return await poll_task_family_snapshot(
            self,
            input_data,
            run_id,
            report_dirs,
            poll_state,
        )

    def _remember_run_task_ids(
        self,
        run_id: str,
        tasks: list[dict[str, object]],
    ) -> None:
        if not tasks:
            return
        task_ids = self.run_task_ids.setdefault(run_id, set())
        for task in tasks:
            task_id = task.get("taskId")
            if isinstance(task_id, str):
                task_ids.add(task_id)

    @staticmethod
    def _task_family_summary(tasks: list[dict[str, object]]) -> list[dict[str, object]]:
        summary: list[dict[str, object]] = []
        for task in tasks[:20]:
            summary.append(
                {
                    "taskId": task.get("taskId"),
                    "runtime": task.get("runtime"),
                    "status": task.get("status"),
                    "sourceId": task.get("sourceId"),
                    "runId": task.get("runId"),
                }
            )
        return summary

    async def _poll_background_completion(
        self,
        input_data: AgentRunCreate,
        run_id: str,
        initial_output: str,
        report_dirs: set[str] | None = None,
        poll_state: dict[str, object] | None = None,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        report_dirs = report_dirs or set()
        report_dirs.update(self._extract_report_dirs(initial_output))
        poll_state = poll_state or self._new_poll_state()
        wait_seconds = self._background_wait_timeout_seconds(self._artifact_filter_key(input_data))
        deadline = monotonic() + wait_seconds
        poll_interval = 8

        yield self._stage_event(
            run_id,
            "stage_started",
            "OpenClaw entered a background workflow; tracking task family and artifacts.",
            int(poll_state.get("progress", 20)),
        )
        poll_state["last_visible_emit_at"] = monotonic()

        while monotonic() < deadline:
            events = await self._poll_task_family_snapshot(
                input_data,
                run_id,
                report_dirs,
                poll_state,
            )
            for event in events:
                yield event
            if self._primary_output_artifact_paths(self._artifact_filter_key(input_data)):
                return
            await asyncio.sleep(poll_interval)

        raise RuntimeError(
            "OpenClaw background workflow did not produce a final artifact before "
            f"timeout ({wait_seconds} seconds)."
        )


    def _background_wait_timeout_seconds(self, skill_key: str | None) -> int:
        minimum_by_skill = {
            "deep_research": 45 * 60,
            "ppt_generation": 30 * 60,
            "html_generation": 30 * 60,
            "data_analysis": 20 * 60,
            "u1_image": 20 * 60,
        }
        return max(self.command_timeout_seconds, minimum_by_skill.get(skill_key or "", 0))

    @staticmethod
    def _no_task_family_timeout_seconds(skill_key: str | None) -> int:
        if skill_key == "ppt_generation":
            return 25 * 60
        if skill_key == "html_generation":
            return 20 * 60
        if skill_key == "deep_research":
            return 6 * 60
        return 0

    @staticmethod
    def _no_artifact_timeout_seconds(skill_key: str | None) -> int:
        if skill_key == "ppt_generation":
            return 25 * 60
        if skill_key == "html_generation":
            return 20 * 60
        if skill_key == "deep_research":
            return 12 * 60
        return 0

    @staticmethod
    def _failed_background_task_label(tasks: list[dict[str, object]]) -> str | None:
        failed_statuses = {"failed", "timed_out", "cancelled", "lost"}
        for task in tasks:
            status = str(task.get("status") or "").lower()
            if status in failed_statuses:
                label = str(task.get("label") or "").strip()
                if not label:
                    raw_task = str(task.get("task") or "").strip()
                    label = OpenClawAdapter._compact_label(raw_task, max_chars=240)
                return label or status or "unknown OpenClaw task failure"
        return None

    @staticmethod
    def _is_recoverable_failed_task(skill_key: str | None, label: str) -> bool:
        normalized = label.lower()
        if skill_key == "ppt_generation" and "html-generator" in normalized:
            return True
        return False

    def _create_fallback_artifact_from_output(
        self,
        input_data: AgentRunCreate,
        run_id: str,
        output: str,
    ) -> None:
        content = output.strip()
        artifact_filter_key = self._artifact_filter_key(input_data)
        if artifact_filter_key not in {"data_analysis", "deep_research"}:
            return
        if len(content) < 80:
            return
        if "```json" in content.lower() and "artifact_paths" in content:
            return

        root = Path(__file__).resolve().parents[4]
        artifact_dir = root / "runtime" / "openclaw-runs" / run_id / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        title = "OpenClaw research report"
        if artifact_filter_key == "data_analysis":
            title = "OpenClaw data analysis"
        file_path = artifact_dir / f"{safe_file_stem(title)}.md"
        file_path.write_text(content, encoding="utf-8")
        self._remember_artifact_ref(
            AgentArtifactRef(
                path=str(file_path),
                artifact_type="markdown_report",
                run_id=run_id,
                source_dir=str(artifact_dir),
                title=title,
            )
        )

    def _stage_event(
        self,
        run_id: str,
        event_type: str,
        label: str,
        progress: int,
    ) -> AgentRunEvent:
        return AgentRunEvent(
            run_id=run_id,
            event_type=event_type,
            status="running",
            progress=progress,
            payload={
                "protocol": "openclaw.cli.v1",
                "mode": self.mode,
            },
            step=AgentRunStep(
                id=f"{run_id}_openclaw_{event_type}",
                label=label,
                status="running",
                timestamp=now_iso(),
            ),
        )
