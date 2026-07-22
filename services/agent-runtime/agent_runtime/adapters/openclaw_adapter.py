import asyncio
import json
import os
import re
import shlex
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from ..schemas import AgentArtifactRef, AgentRun, AgentRunCreate, AgentRunEvent, AgentRunStep
from .base import AgentRuntimeAdapter


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


OPENCLAW_SKILL_MAPPING = {
    "data_analysis": {
        "name": "OpenClaw data analysis",
        "capability": "data_analysis",
        "instruction": (
            "Run OpenClaw's data analysis workflow. Prefer attached or referenced CSV/XLSX/table "
            "artifacts, inspect the data, summarize findings, and create a concise report or table."
        ),
        "artifact_type_hint": "data_table or markdown_report",
    },
    "deep_research": {
        "name": "OpenClaw research",
        "capability": "research",
        "instruction": (
            "Run OpenClaw's research workflow. Search and synthesize evidence, "
            "keep citations clear, "
            "and produce one final report instead of scattering the answer across sub-reports."
        ),
        "artifact_type_hint": "markdown_report or html_page",
    },
    "ppt_generation": {
        "name": "OpenClaw presentation generation",
        "capability": "presentation",
        "instruction": (
            "Run OpenClaw's presentation generation workflow. Use the most relevant source report "
            "or HTML content, generate slide pages, and export a PPTX deliverable when possible."
        ),
        "artifact_type_hint": "ppt_deck and optional html_page fallback",
    },
    "html_generation": {
        "name": "OpenClaw HTML report generation",
        "capability": "html_report_generation",
        "instruction": (
            "Run OpenClaw's report-html-v2 workflow. Use the most relevant source Markdown "
            "report path from the WebAgent runtime context, generate a standalone HTML report, "
            "and do not redo research unless the source report is missing."
        ),
        "artifact_type_hint": "html_page",
    },
    "u1_image": {
        "name": "OpenClaw image generation",
        "capability": "image_generation",
        "instruction": (
            "Run OpenClaw's image generation workflow. Treat U1 as the image "
            "generation capability, "
            "not as a reference image name. Generate image files matching the user's request."
        ),
        "artifact_type_hint": "image_result",
    },
}


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
        skills_dir: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.cli_path = cli_path
        self.command_timeout_seconds = command_timeout_seconds
        self.mode = mode
        self.skills_dir = skills_dir
        self.active_processes: dict[str, asyncio.subprocess.Process] = {}
        self.cancelled_run_ids: set[str] = set()
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
        poll_state = self._new_poll_state()
        report_dirs = self._extract_report_dirs(input_data.content)

        if input_data.skill_key:
            skill_name = self._skill_mapping(input_data.skill_key).get(
                "name",
                input_data.skill_key,
            )
            yield self._stage_event(
                run_id,
                "stage_started",
                f"OpenClaw is running {skill_name}.",
                10,
            )

        process = await self._start_agent_process(input_data, run_id)
        cli_timed_out = False
        stdout = b""
        stderr = b""
        communicate_task = asyncio.create_task(process.communicate())
        try:
            if input_data.skill_key:
                started_at = monotonic()
                while True:
                    try:
                        stdout, stderr = await asyncio.wait_for(
                            asyncio.shield(communicate_task),
                            timeout=self._foreground_poll_interval_seconds(input_data.skill_key),
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
                        if self._primary_output_artifact_paths():
                            final_artifact_found = True
                            stdout, stderr = await self._kill_and_collect_output(
                                process,
                                communicate_task,
                            )
                            break
            else:
                stdout, stderr = await asyncio.wait_for(
                    communicate_task,
                    timeout=self.command_timeout_seconds,
                )
        except TimeoutError as exc:
            cli_timed_out = True
            if input_data.skill_key:
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

        raw_stdout = stdout.decode("utf-8", errors="replace")
        raw_stderr = stderr.decode("utf-8", errors="replace")
        self._remember_artifact_paths(raw_stdout)
        self._remember_artifact_paths(raw_stderr)
        output = self._extract_output(raw_stdout, raw_stderr)
        structured_artifacts = self._extract_structured_artifacts(
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
            final_artifact_found = bool(self._primary_output_artifact_paths())

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
        }

        if process.returncode != 0 and not cli_timed_out and not final_artifact_found:
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
                    "artifact": self._artifact_to_payload(artifact),
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
                "artifacts": [self._artifact_to_payload(item) for item in self.last_artifacts],
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
        )
        self.active_processes[run_id] = process
        return process

    @staticmethod
    async def _kill_and_collect_output(
        process: asyncio.subprocess.Process,
        communicate_task: asyncio.Task,
    ) -> tuple[bytes, bytes]:
        if process.returncode is None:
            process.kill()
        try:
            return await communicate_task
        except TimeoutError:
            return await process.communicate()

    def _build_agent_cli_args(self, input_data: AgentRunCreate) -> list[str]:
        timeout = str(max(1, self.command_timeout_seconds))
        args = [
            "agent",
            "--agent",
            self.agent_id,
            "--message",
            self._build_openclaw_message(input_data),
            "--json",
            "--timeout",
            timeout,
        ]
        if self.mode == "local_cli":
            args.insert(1, "--local")
        if input_data.session_id:
            args.extend(["--session-id", input_data.session_id])
        return self._build_cli_args(args)

    @staticmethod
    def _skill_mapping(skill_key: str | None) -> dict[str, str]:
        if not skill_key:
            return {}
        return OPENCLAW_SKILL_MAPPING.get(skill_key, {})

    def _build_openclaw_message(self, input_data: AgentRunCreate) -> str:
        mapping = self._skill_mapping(input_data.skill_key)
        if not mapping:
            return input_data.content

        protocol_instruction = (
            "When artifacts are created, return a JSON-compatible artifact protocol with: "
            "artifact_paths, artifact_type, source_dir, run_id, and title. "
            f"Expected artifact_type: {mapping['artifact_type_hint']}."
        )
        return (
            f"[WebAgent skill mapping]\n"
            f"webagent_skill={input_data.skill_key}\n"
            f"webagent_run_id={input_data.run_id or input_data.session_id}\n"
            f"openclaw_capability={mapping['capability']}\n"
            f"{mapping['instruction']}\n"
            f"{protocol_instruction}\n\n"
            f"[User request]\n{input_data.content}"
        )

    def _build_local_cli_args(self, input_data: AgentRunCreate) -> list[str]:
        previous_mode = self.mode
        self.mode = "local_cli"
        try:
            return self._build_agent_cli_args(input_data)
        finally:
            self.mode = previous_mode

    def _build_cli_args(self, args: list[str]) -> list[str]:
        if os.name == "nt" and self.cli_path == "openclaw":
            command = " ".join(shlex.quote(str(arg)) for arg in ["openclaw", *args])
            command = self._with_runtime_env(
                command,
                {"OPENCLAW_SKILLS_DIR": self.skills_dir} if self.skills_dir else None,
            )
            return ["wsl.exe", "--", "bash", "-lc", command]
        return [self.cli_path, *args]

    def _build_shell_args(self, command: str) -> list[str]:
        command = self._with_runtime_env(
            command,
            {"OPENCLAW_SKILLS_DIR": self.skills_dir} if self.skills_dir else None,
        )
        if os.name == "nt":
            return ["wsl.exe", "--", "bash", "-lc", command]
        return ["bash", "-lc", command]

    @staticmethod
    def _with_runtime_env(command: str, extra_env: dict[str, str | None] | None = None) -> str:
        extra_exports = ""
        for key, value in (extra_env or {}).items():
            if value:
                extra_exports += f"export {key}=${{{key}:-{shlex.quote(value)}}}; "
        return (
            "for __f in ~/.hermes/.env ~/.openclaw/.env; do "
            "[ -f \"$__f\" ] || continue; "
            "while IFS= read -r __line || [ -n \"$__line\" ]; do "
            "__line=${__line%$'\\r'}; "
            "case \"$__line\" in ''|\\#*) continue;; esac; "
            "__key=${__line%%=*}; "
            "if [[ \"$__key\" =~ ^[A-Za-z_][A-Za-z0-9_]*$ && \"$__key\" != PATH ]]; then "
            "export \"$__line\"; "
            "fi; "
            "done < \"$__f\"; "
            "done; "
            "unset __f __line __key; "
            f"{extra_exports}"
            f"{command}"
        )

    def _reset_last_state(self) -> None:
        self.last_artifact_paths = []
        self.last_artifacts = []
        self.last_diagnostics = {}

    def _remember_artifact_paths(self, text: str) -> None:
        for path in self._extract_paths(text):
            self._remember_artifact_path(path)

    def _remember_artifact_path(self, path: str) -> None:
        self._remember_artifact_ref(AgentArtifactRef(path=path))

    def _remember_artifact_ref(self, artifact: AgentArtifactRef) -> None:
        path = artifact.path
        if self._is_openclaw_bootstrap_path(path):
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
                artifact_type=artifact.artifact_type or self._guess_artifact_type(path),
                run_id=artifact.run_id,
                source_dir=artifact.source_dir or self._source_dir_from_path(path),
                title=artifact.title or self._title_from_path(path),
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
            await process.wait()
            return None

        text = self._first_json_like_text(stdout, stderr)
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

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
        if not report_dirs:
            return []
        quoted_dirs = " ".join(shlex.quote(path) for path in sorted(report_dirs))
        suffix_expr = (
            r"\( -iname '*.md' -o -iname '*.html' -o -iname '*.htm' "
            r"-o -iname '*.pptx' -o -iname '*.png' -o -iname '*.jpg' "
            r"-o -iname '*.jpeg' -o -iname '*.webp' -o -iname '*.csv' "
            r"-o -iname '*.xlsx' -o -iname '*.json' \)"
        )
        command = (
            f"for __dir in {quoted_dirs}; do "
            "[ -d \"$__dir\" ] || continue; "
            f"find \"$__dir\" -maxdepth 4 -type f {suffix_expr} -print; "
            "done"
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
            return []
        paths = [
            line.strip()
            for line in stdout.decode("utf-8", errors="replace").splitlines()
            if line.strip()
        ]
        return [
            path
            for path in paths
            if Path(path).suffix.lower() == ".json" or self._is_primary_output_artifact(path)
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
    def _task_text(task: dict[str, object]) -> str:
        return OpenClawAdapter._repair_mojibake(
            json.dumps(task, ensure_ascii=False),
        )

    @staticmethod
    def _repair_mojibake(text: str) -> str:
        if not any(marker in text for marker in ("å", "ç", "æ", "ä", "è", "é", "ï")):
            return text
        try:
            repaired = text.encode("latin1").decode("utf-8")
        except UnicodeError:
            return text
        chinese_count = sum(1 for char in repaired if "\u4e00" <= char <= "\u9fff")
        original_chinese_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        return repaired if chinese_count > original_chinese_count else text

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
                report_dirs.update(self._extract_report_dirs(self._task_text(task)))
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
        if not input_data.skill_key:
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
    def _summarize_task_label(task: dict[str, object]) -> str:
        task_text = OpenClawAdapter._repair_mojibake(str(task.get("task") or ""))
        status = str(task.get("status") or "running")
        dimension_match = re.search(r"dimension_id\s*:\s*([A-Za-z0-9_-]+)", task_text)
        dimension_name_match = re.search(
            r"(?:\u7ef4\u5ea6\u540d\u79f0|缁村害鍚嶇О)\s*[:：]\s*([^\n\r]+)",
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
        if "webagent_skill=html_generation" in task_text and status in {"queued", "running"}:
            source_match = re.search(
                r"path=([^\s]+(?:\.md|\.markdown))",
                task_text,
                re.IGNORECASE,
            )
            source_name = Path(source_match.group(1)).name if source_match else "source report"
            return f"OpenClaw is generating an HTML report from {source_name}."
        if "webagent_skill=deep_research" in task_text and status in {"queued", "running"}:
            title_match = re.search(r"《([^》]+)》", task_text)
            title = f"《{title_match.group(1)}》" if title_match else "the research topic"
            return f"OpenClaw is researching {title} and collecting report artifacts."
        if status == "succeeded":
            return f"OpenClaw {runtime} task completed; waiting for child tasks or artifacts."
        return f"OpenClaw {runtime} task status: {status}."

        dimension_match = re.search(r"dimension_id\s*:\s*([A-Za-z0-9_-]+)", task_text)
        dimension_name_match = re.search(r"维度名称\s*[:：]\s*([^\n\r]+)", task_text)
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

        if dimension and status == "running":
            if "status: timed out" in task_text.lower():
                return f"OpenClaw 正在重试或补写 {dimension} 证据文件。"
            if dimension_name:
                return f"OpenClaw 正在调研 {dimension}：{dimension_name}"
            return f"OpenClaw 正在调研 {dimension}。"
        if dimension and status == "succeeded":
            if result:
                return f"OpenClaw 已完成 {dimension}：{result}"
            if dimension_name:
                return f"OpenClaw 已完成 {dimension}：{dimension_name}"
            return f"OpenClaw 已完成 {dimension}。"

        for key in ("progressSummary", "label"):
            value = task.get(key)
            if isinstance(value, str) and value.strip():
                return OpenClawAdapter._compact_label(OpenClawAdapter._repair_mojibake(value))
        runtime = str(task.get("runtime") or "task")
        if status == "succeeded":
            return f"OpenClaw {runtime} 任务已完成，正在等待子任务或最终产物。"
        return f"OpenClaw {runtime} 任务状态：{status}。"

    @staticmethod
    def _compact_label(value: str, max_chars: int = 360) -> str:
        cleaned = OpenClawAdapter._clean_text_output(value)
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
        }

    @staticmethod
    def _foreground_poll_interval_seconds(skill_key: str | None) -> int:
        if skill_key in {"deep_research", "ppt_generation", "html_generation"}:
            return 10
        return 6

    def _primary_output_artifact_paths(self) -> list[str]:
        return [
            path for path in self.last_artifact_paths if self._is_primary_output_artifact(path)
        ]

    async def _poll_task_family_snapshot(
        self,
        input_data: AgentRunCreate,
        run_id: str,
        report_dirs: set[str],
        poll_state: dict[str, object],
    ) -> list[AgentRunEvent]:
        events: list[AgentRunEvent] = []
        tasks_payload = await self._run_openclaw_json_command(
            ["tasks", "list", "--json"],
            timeout_seconds=20,
        )
        tasks = []
        if isinstance(tasks_payload, dict):
            raw_tasks = tasks_payload.get("tasks")
            tasks = raw_tasks if isinstance(raw_tasks, list) else []

        matching_tasks = self._matching_task_family(
            [task for task in tasks if isinstance(task, dict)],
            input_data,
            report_dirs,
        )
        for task in matching_tasks:
            report_dirs.update(self._extract_report_dirs(self._task_text(task)))
        if not self._primary_output_artifact_paths():
            report_dirs.update(await self._discover_report_dirs_from_input(input_data))

        failed_task_label = self._failed_background_task_label(matching_tasks)
        if failed_task_label:
            raise RuntimeError(
                "OpenClaw task family failed before producing a final artifact: "
                f"{failed_task_label}"
            )

        artifact_paths = await self._find_report_artifacts(report_dirs)
        for path in artifact_paths:
            self._remember_artifact_path(path)

        progress = int(poll_state.get("progress", 20))
        last_artifact_count = int(poll_state.get("last_artifact_count", 0))
        if len(self.last_artifact_paths) > last_artifact_count:
            poll_state["last_artifact_count"] = len(self.last_artifact_paths)
            debug_count = sum(
                1 for path in self.last_artifact_paths if Path(path).suffix.lower() == ".json"
            )
            primary_paths = self._primary_output_artifact_paths()
            progress = 90 if primary_paths else min(88, progress + 6)
            poll_state["progress"] = progress
            if primary_paths:
                for artifact in self.last_artifacts:
                    artifact.run_id = artifact.run_id or run_id
                events.append(
                    AgentRunEvent(
                        run_id=run_id,
                        event_type="artifact_found",
                        status="running",
                        progress=90,
                        payload={
                            "protocol": "openclaw.cli.v1",
                            "mode": self.mode,
                            "artifact_paths": list(self.last_artifact_paths),
                            "artifacts": [
                                self._artifact_to_payload(item) for item in self.last_artifacts
                            ],
                            "reportDirs": sorted(report_dirs),
                            "taskFamily": self._task_family_summary(matching_tasks),
                        },
                        step=AgentRunStep(
                            id=f"{run_id}_openclaw_artifact_found",
                            label=f"OpenClaw final artifact found: {primary_paths[-1]}",
                            status="completed",
                            timestamp=now_iso(),
                        ),
                    )
                )
            elif debug_count:
                events.append(
                    self._stage_event(
                        run_id,
                        "stage_update",
                        (
                            f"OpenClaw has generated {debug_count} intermediate evidence "
                            "file(s); waiting for the final deliverable."
                        ),
                        progress,
                    )
                )

        running_tasks = [
            task for task in matching_tasks if task.get("status") in {"queued", "running"}
        ]
        if matching_tasks:
            display_task = next(iter(running_tasks), matching_tasks[0])
            label = self._summarize_task_label(display_task)
        elif report_dirs:
            label = "OpenClaw is still working; watching the report directory."
        else:
            label = "OpenClaw is still working; waiting for task progress."

        now = monotonic()
        last_label = str(poll_state.get("last_label", ""))
        last_emit_at = float(poll_state.get("last_visible_emit_at", 0.0))
        should_emit_heartbeat = now - last_emit_at >= 60
        evidence_count = sum(
            1 for path in self.last_artifact_paths if Path(path).suffix.lower() == ".json"
        )
        should_emit_evidence_heartbeat = should_emit_heartbeat and evidence_count > 0
        if label != last_label or should_emit_evidence_heartbeat:
            poll_state["last_label"] = label
            poll_state["last_visible_emit_at"] = now
            progress = min(85, int(poll_state.get("progress", 20)) + 8)
            poll_state["progress"] = progress
            if should_emit_evidence_heartbeat and label == last_label:
                label = (
                    f"{label} Found {evidence_count} intermediate evidence file(s); "
                    "still waiting for the final deliverable."
                )
            events.append(self._stage_event(run_id, "stage_update", label, progress))

        self.last_diagnostics.update(
            {
                "reportDirs": sorted(report_dirs),
                "matchingTaskCount": len(matching_tasks),
                "runningTaskCount": len(running_tasks),
                "artifactPaths": list(self.last_artifact_paths),
                "artifactCount": len(self.last_artifact_paths),
                "lastStage": label,
            }
        )
        return events

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
        wait_seconds = self._background_wait_timeout_seconds(input_data.skill_key)
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
            if self._primary_output_artifact_paths():
                return
            await asyncio.sleep(poll_interval)

        raise RuntimeError(
            "OpenClaw background workflow did not produce a final artifact before "
            f"timeout ({wait_seconds} seconds)."
        )

        report_dirs = self._extract_report_dirs(initial_output)
        wait_seconds = self._background_wait_timeout_seconds(input_data.skill_key)
        deadline = monotonic() + wait_seconds
        last_label = ""
        last_artifact_count = 0
        last_visible_emit_at = 0.0
        progress = 20
        poll_interval = 8
        heartbeat_interval = 60

        yield self._stage_event(
            run_id,
            "stage_started",
            "OpenClaw 已进入后台长任务，正在跟踪子任务和产物目录。",
            progress,
        )
        last_visible_emit_at = monotonic()

        while monotonic() < deadline:
            tasks_payload = await self._run_openclaw_json_command(
                ["tasks", "list", "--json"],
                timeout_seconds=20,
            )
            tasks = []
            if isinstance(tasks_payload, dict):
                raw_tasks = tasks_payload.get("tasks")
                tasks = raw_tasks if isinstance(raw_tasks, list) else []

            matching_tasks = self._matching_task_family(
                [task for task in tasks if isinstance(task, dict)],
                input_data,
                report_dirs,
            )
            for task in matching_tasks:
                report_dirs.update(self._extract_report_dirs(self._task_text(task)))

            failed_task_label = self._failed_background_task_label(matching_tasks)
            if failed_task_label:
                raise RuntimeError(
                    "OpenClaw background workflow failed before producing a final artifact: "
                    f"{failed_task_label}"
                )

            artifact_paths = await self._find_report_artifacts(report_dirs)
            for path in artifact_paths:
                self._remember_artifact_path(path)

            if len(self.last_artifact_paths) > last_artifact_count:
                last_artifact_count = len(self.last_artifact_paths)
                debug_count = sum(
                    1
                    for path in self.last_artifact_paths
                    if Path(path).suffix.lower() == ".json"
                )
                if debug_count:
                    progress = min(88, progress + 6)
                    yield self._stage_event(
                        run_id,
                        "stage_update",
                        f"OpenClaw generated {debug_count} intermediate evidence file(s).",
                        progress,
                    )

            primary_artifacts = [
                path for path in self.last_artifact_paths if self._is_primary_output_artifact(path)
            ]
            if primary_artifacts:
                for artifact in self.last_artifacts:
                    artifact.run_id = artifact.run_id or run_id
                yield AgentRunEvent(
                    run_id=run_id,
                    event_type="artifact_found",
                    status="running",
                    progress=90,
                    payload={
                        "protocol": "openclaw.cli.v1",
                        "mode": self.mode,
                        "artifact_paths": list(self.last_artifact_paths),
                        "artifacts": [
                            self._artifact_to_payload(item) for item in self.last_artifacts
                        ],
                        "reportDirs": sorted(report_dirs),
                        "backgroundWait": True,
                    },
                    step=AgentRunStep(
                        id=f"{run_id}_openclaw_background_artifacts",
                        label=f"OpenClaw generated artifact: {primary_artifacts[-1]}",
                        status="completed",
                        timestamp=now_iso(),
                    ),
                )
                return

            running_tasks = [
                task
                for task in matching_tasks
                if task.get("status") in {"queued", "running"}
            ]
            if matching_tasks:
                running_or_latest_task = next(
                    (
                        task
                        for task in matching_tasks
                        if task.get("status") in {"queued", "running"}
                    ),
                    matching_tasks[0],
                )
                label = self._summarize_task_label(running_or_latest_task)
            elif report_dirs:
                label = "OpenClaw is still working; waiting for report files."
            else:
                label = "OpenClaw is still working; waiting for task progress."

            now = monotonic()
            should_emit_heartbeat = now - last_visible_emit_at >= heartbeat_interval
            if label != last_label or should_emit_heartbeat:
                last_label = label
                last_visible_emit_at = now
                progress = min(85, progress + 8)
                if should_emit_heartbeat and label == last_label:
                    evidence_count = sum(
                        1
                        for path in self.last_artifact_paths
                        if Path(path).suffix.lower() == ".json"
                    )
                    if evidence_count:
                        label = (
                            f"{label} 已发现 {evidence_count} 个中间证据文件，"
                            "继续等待最终 Markdown 报告。"
                        )
                yield self._stage_event(run_id, "stage_update", label, progress)

            if matching_tasks and not running_tasks and report_dirs:
                await asyncio.sleep(poll_interval)
            else:
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
    def _extract_output(stdout: str, stderr: str) -> str:
        for data in (stdout, stderr):
            cleaned = OpenClawAdapter._clean_text_output(data)
            if not cleaned:
                continue
            parsed_output = OpenClawAdapter._extract_json_output(cleaned)
            if parsed_output:
                return parsed_output
            return cleaned
        return ""

    @staticmethod
    def _extract_json_output(text: str) -> str | None:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None

        result = parsed.get("result")
        if isinstance(result, dict):
            result_output = OpenClawAdapter._extract_json_output(
                json.dumps(result, ensure_ascii=False)
            )
            if result_output:
                return result_output

        for key in ("output", "reply", "message", "content", "text"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        payloads = parsed.get("payloads")
        if isinstance(payloads, list):
            parts = []
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue
                text_value = payload.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    parts.append(text_value.strip())
            if parts:
                return "\n".join(parts)

        return json.dumps(parsed, ensure_ascii=False)

    @staticmethod
    def _extract_structured_artifact_paths(stdout: str, stderr: str) -> list[str]:
        return [
            artifact.path
            for artifact in OpenClawAdapter._extract_structured_artifacts(stdout, stderr)
        ]

    @staticmethod
    def _extract_structured_artifacts(stdout: str, stderr: str) -> list[AgentArtifactRef]:
        artifacts: list[AgentArtifactRef] = []
        seen: set[str] = set()
        for text in (stdout, stderr):
            cleaned = OpenClawAdapter._clean_text_output(text)
            if not cleaned:
                continue
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                continue
            OpenClawAdapter._collect_artifact_refs(parsed, artifacts, seen)
        return artifacts

    @staticmethod
    def _extract_structured_artifact_paths_legacy(stdout: str, stderr: str) -> list[str]:
        paths: list[str] = []
        for text in (stdout, stderr):
            cleaned = OpenClawAdapter._clean_text_output(text)
            if not cleaned:
                continue
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                continue
            OpenClawAdapter._collect_artifact_paths(parsed, paths)
        return paths

    @staticmethod
    def _collect_artifact_refs(
        value: object,
        artifacts: list[AgentArtifactRef],
        seen: set[str],
        inherited: dict[str, str | None] | None = None,
    ) -> None:
        inherited = inherited or {}
        if isinstance(value, dict):
            artifact_type = OpenClawAdapter._string_value(
                value,
                "artifact_type",
                "artifactType",
                "type",
            ) or inherited.get("artifact_type")
            source_dir = OpenClawAdapter._string_value(
                value,
                "source_dir",
                "sourceDir",
            ) or inherited.get("source_dir")
            run_id = OpenClawAdapter._string_value(value, "run_id", "runId") or inherited.get(
                "run_id"
            )
            title = OpenClawAdapter._string_value(value, "title", "name") or inherited.get("title")
            context = {
                "artifact_type": artifact_type,
                "source_dir": source_dir,
                "run_id": run_id,
                "title": title,
            }

            direct_paths = OpenClawAdapter._artifact_paths_from_mapping(value)
            for path in direct_paths:
                if path in seen:
                    continue
                seen.add(path)
                artifacts.append(
                    AgentArtifactRef(
                        path=path,
                        artifact_type=artifact_type,
                        run_id=run_id,
                        source_dir=source_dir,
                        title=title,
                    )
                )

            for item in value.values():
                OpenClawAdapter._collect_artifact_refs(item, artifacts, seen, context)
        elif isinstance(value, list):
            for item in value:
                OpenClawAdapter._collect_artifact_refs(item, artifacts, seen, inherited)

    @staticmethod
    def _artifact_paths_from_mapping(value: dict) -> list[str]:
        paths: list[str] = []
        for key, item in value.items():
            normalized_key = key.lower()
            if normalized_key in {
                "artifact_path",
                "artifact_paths",
                "artifactpath",
                "path",
                "paths",
                "filepath",
                "file_path",
                "mediaurl",
                "media_url",
            }:
                paths.extend(OpenClawAdapter._extract_paths_from_value(item))
        return paths

    @staticmethod
    def _extract_paths_from_value(value: object) -> list[str]:
        if isinstance(value, str):
            return OpenClawAdapter._extract_paths(value)
        if isinstance(value, list):
            paths: list[str] = []
            for item in value:
                paths.extend(OpenClawAdapter._extract_paths_from_value(item))
            return paths
        if isinstance(value, dict):
            paths: list[str] = []
            for item in value.values():
                paths.extend(OpenClawAdapter._extract_paths_from_value(item))
            return paths
        return []

    @staticmethod
    def _string_value(value: dict, *keys: str) -> str | None:
        for key in keys:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        return None

    @staticmethod
    def _collect_artifact_paths(value: object, paths: list[str]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized_key = key.lower()
                if normalized_key in {
                    "artifact_path",
                    "artifact_paths",
                    "artifactpath",
                    "path",
                    "paths",
                    "filepath",
                    "file_path",
                    "mediaurl",
                    "media_url",
                } and isinstance(item, str):
                    paths.extend(OpenClawAdapter._extract_paths(item))
                elif normalized_key in {"artifact_paths", "paths"} and isinstance(item, list):
                    for path in item:
                        if isinstance(path, str):
                            paths.extend(OpenClawAdapter._extract_paths(path))
                else:
                    OpenClawAdapter._collect_artifact_paths(item, paths)
        elif isinstance(value, list):
            for item in value:
                OpenClawAdapter._collect_artifact_paths(item, paths)

    @staticmethod
    def _clean_text_output(text: str) -> str:
        lines = []
        ansi_pattern = re.compile(r"\x1b\[[0-9;]*m")
        for line in text.splitlines():
            cleaned = ansi_pattern.sub("", line).strip()
            if not cleaned:
                continue
            if cleaned.startswith("[skills]"):
                continue
            lines.append(cleaned)
        return "\n".join(lines).strip()

    @staticmethod
    def _extract_paths(text: str) -> list[str]:
        pattern = re.compile(
            r"(?P<path>(?:[A-Za-z]:\\|/mnt/[a-z]/|/)[^\s'\"<>]+"
            r"\.(?:md|markdown|html|htm|pptx|ppt|png|jpg|jpeg|webp|csv|xlsx|json))",
            re.IGNORECASE,
        )
        return [match.group("path").rstrip(".,;:") for match in pattern.finditer(text)]

    @staticmethod
    def _guess_artifact_type(path: str) -> str | None:
        suffix = Path(path).suffix.lower()
        if suffix in {".md", ".markdown"}:
            return "markdown_report"
        if suffix in {".html", ".htm"}:
            return "html_page"
        if suffix in {".ppt", ".pptx"}:
            return "ppt_deck"
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            return "image_result"
        if suffix in {".csv", ".xlsx"}:
            return "data_table"
        if suffix == ".json":
            return "debug_json"
        return None

    @staticmethod
    def _source_dir_from_path(path: str) -> str | None:
        return str(Path(path).parent)

    @staticmethod
    def _title_from_path(path: str) -> str:
        return Path(path).stem

    @staticmethod
    def _safe_file_stem(value: str) -> str:
        cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "-", value.strip()).strip("-")
        return cleaned[:80] or "openclaw-report"

    def _create_fallback_artifact_from_output(
        self,
        input_data: AgentRunCreate,
        run_id: str,
        output: str,
    ) -> None:
        content = output.strip()
        if input_data.skill_key not in {"data_analysis", "deep_research"}:
            return
        if len(content) < 80:
            return
        if "```json" in content.lower() and "artifact_paths" in content:
            return

        root = Path(__file__).resolve().parents[4]
        artifact_dir = root / "runtime" / "openclaw-runs" / run_id / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        title = "OpenClaw research report"
        if input_data.skill_key == "data_analysis":
            title = "OpenClaw data analysis"
        file_path = artifact_dir / f"{self._safe_file_stem(title)}.md"
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

    @staticmethod
    def _is_openclaw_bootstrap_path(path: str) -> bool:
        normalized = path.replace("\\", "/")
        bootstrap_names = {
            "AGENTS.md",
            "SOUL.md",
            "TOOLS.md",
            "IDENTITY.md",
            "USER.md",
            "HEARTBEAT.md",
            "BOOTSTRAP.md",
        }
        if "/.openclaw/workspace/" not in normalized:
            return False
        return normalized.rsplit("/", 1)[-1] in bootstrap_names

    @staticmethod
    def _artifact_to_payload(artifact: AgentArtifactRef) -> dict[str, object]:
        return {
            "artifact_paths": [artifact.path],
            "artifact_path": artifact.path,
            "artifact_type": artifact.artifact_type,
            "run_id": artifact.run_id,
            "source_dir": artifact.source_dir,
            "title": artifact.title,
        }

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
