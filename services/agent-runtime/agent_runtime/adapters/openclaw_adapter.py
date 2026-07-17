import asyncio
import json
import os
import re
import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import AsyncGenerator

from ..schemas import AgentArtifactRef, AgentRun, AgentRunCreate, AgentRunEvent, AgentRunStep
from .base import AgentRuntimeAdapter


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class OpenClawAdapter(AgentRuntimeAdapter):
    """Adapter for OpenClaw's CLI/Gateway agent interface.

    The first implementation uses `openclaw agent --local` because it works without
    keeping a Gateway process alive. The public adapter surface mirrors Hermes so
    WebAgent can switch runtimes through the same AgentRun/SSE pipeline.
    """

    def __init__(
        self,
        base_url: str = "ws://127.0.0.1:18789",
        *,
        agent_id: str = "main",
        cli_path: str = "openclaw",
        command_timeout_seconds: int = 600,
        mode: str = "local_cli",
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.cli_path = cli_path
        self.command_timeout_seconds = command_timeout_seconds
        self.mode = mode
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
            except asyncio.TimeoutError:
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

        process = await self._start_agent_process(input_data, run_id)
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.command_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
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
        self.last_diagnostics = {
            "adapter": "openclaw",
            "mode": self.mode,
            "exitCode": process.returncode,
            "stderrTail": raw_stderr[-2000:],
            "stdoutTail": raw_stdout[-2000:],
            "artifactPaths": list(self.last_artifact_paths),
        }

        if process.returncode != 0:
            raise RuntimeError(
                f"OpenClaw exited with code {process.returncode}: "
                f"{(raw_stderr or raw_stdout).strip()[-1000:]}"
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
            *self._build_local_cli_args(input_data),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.active_processes[run_id] = process
        return process

    def _build_local_cli_args(self, input_data: AgentRunCreate) -> list[str]:
        timeout = str(max(1, self.command_timeout_seconds))
        args = [
            "agent",
            "--local",
            "--agent",
            self.agent_id,
            "--message",
            input_data.content,
            "--json",
            "--timeout",
            timeout,
        ]
        if input_data.session_id:
            args.extend(["--session-id", input_data.session_id])
        return self._build_cli_args(args)

    def _build_cli_args(self, args: list[str]) -> list[str]:
        if os.name == "nt" and self.cli_path == "openclaw":
            command = " ".join(shlex.quote(str(arg)) for arg in ["openclaw", *args])
            return ["wsl.exe", "--", "bash", "-lc", command]
        return [self.cli_path, *args]

    def _reset_last_state(self) -> None:
        self.last_artifact_paths = []
        self.last_artifacts = []
        self.last_diagnostics = {}

    def _remember_artifact_paths(self, text: str) -> None:
        for path in self._extract_paths(text):
            if self._is_openclaw_bootstrap_path(path):
                continue
            if path in self.last_artifact_paths:
                continue
            self.last_artifact_paths.append(path)
            self.last_artifacts.append(
                AgentArtifactRef(
                    path=path,
                    artifact_type=self._guess_artifact_type(path),
                    source_dir=str(Path(path).parent) if not path.startswith("/mnt/") else None,
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
    def _artifact_to_payload(artifact: AgentArtifactRef) -> dict[str, str | None]:
        return {
            "artifact_path": artifact.path,
            "artifact_type": artifact.artifact_type,
            "run_id": artifact.run_id,
            "source_dir": artifact.source_dir,
        }
