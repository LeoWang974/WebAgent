import asyncio
import json
import os
import re
import shlex
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

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
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.command_timeout_seconds,
            )
        except TimeoutError as exc:
            await self.cancel_run(run_id)
            self.last_diagnostics = {
                "adapter": "openclaw",
                "mode": self.mode,
                "timeoutSeconds": self.command_timeout_seconds,
            }
            raise RuntimeError("OpenClaw agent command timed out.") from exc
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
        self.last_diagnostics = {
            "adapter": "openclaw",
            "mode": self.mode,
            "exitCode": process.returncode,
            "stderrTail": raw_stderr[-2000:],
            "stdoutTail": raw_stdout[-2000:],
            "artifactPaths": list(self.last_artifact_paths),
            "artifactCount": len(self.last_artifact_paths),
        }

        if process.returncode != 0:
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
        if suffix in {".csv", ".xlsx", ".json"}:
            return "data_table"
        return None

    @staticmethod
    def _source_dir_from_path(path: str) -> str | None:
        return str(Path(path).parent)

    @staticmethod
    def _title_from_path(path: str) -> str:
        return Path(path).stem

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
