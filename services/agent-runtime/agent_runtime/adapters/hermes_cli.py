import asyncio
import logging
import os
import re
import shlex
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import AsyncGenerator, Optional, Tuple


logger = logging.getLogger(__name__)

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
ARTIFACT_PATH_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:\\|/mnt/[a-zA-Z]/|/home/|/tmp/)[^\"'<>|`\r\n]+?\.(?:md|html?|pptx|png|jpe?g|csv|xlsx))",
    re.IGNORECASE,
)
BOX_CODEPOINTS = {
    0x2500,
    0x2502,
    0x250C,
    0x2510,
    0x2514,
    0x2518,
    0x251C,
    0x2524,
    0x252C,
    0x2534,
    0x253C,
    0x2550,
    0x2551,
    0x2554,
    0x2557,
    0x255A,
    0x255D,
    0x256D,
    0x256E,
    0x256F,
    0x2570,
}


@dataclass(frozen=True)
class HermesStreamEvent:
    event_type: str
    content: str
    artifact_paths: list[str] = field(default_factory=list)
    artifacts: list[dict[str, str | None]] = field(default_factory=list)
    raw_log_path: str | None = None
    completion_detected: bool = False
    payload: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "protocol": "hermes.stream.v1",
            "hermesEventType": self.event_type,
            "content": self.content,
            "artifact_paths": self.artifact_paths,
            "artifacts": self.artifacts,
            "completionDetected": self.completion_detected,
        }
        if self.raw_log_path:
            payload["rawLogPath"] = self.raw_log_path
        payload.update(self.payload)
        return payload


class HermesCliWrapper:
    def __init__(
        self,
        hermes_path: str = "/home/zhuchangbiaozhu_xyl/.local/bin/hermes",
        hermes_home: str = "/home/zhuchangbiaozhu_xyl/.hermes",
        wsl_distribution: str = "Ubuntu",
    ):
        self.hermes_path = hermes_path
        self.hermes_home = hermes_home
        self.wsl_distribution = wsl_distribution
        self._env = {
            "HERMES_HOME": hermes_home,
            "HERMES_QUIET": "1",
        }
        self.last_artifact_paths: list[str] = []
        self.last_artifacts: list[dict[str, str | None]] = []
        self.last_diagnostics: dict[str, object] = {}
        self.active_processes: dict[str, asyncio.subprocess.Process] = {}
        self.cancelled_run_ids: set[str] = set()

    def _build_wsl_command(
        self,
        args: list[str],
        quiet: bool = True,
        use_pty: bool = False,
    ) -> str:
        env = dict(self._env)
        if not quiet:
            env.pop("HERMES_QUIET", None)

        env_str = " ".join(f"{key}={shlex.quote(value)}" for key, value in env.items())
        quoted_args = " ".join(shlex.quote(arg) for arg in args)
        command = f"{env_str} {quoted_args}".strip()
        if use_pty:
            command = f"script -q -e -c {shlex.quote(command)} /dev/null"
        return f"wsl -d {shlex.quote(self.wsl_distribution)} -- bash -lc {shlex.quote(command)}"

    def _raw_log_path(self) -> Path:
        log_dir = Path(__file__).resolve().parents[4] / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return log_dir / f"hermes-raw-{timestamp}.log"

    def _prompt_file_path(self, question: str, run_id: Optional[str] = None) -> tuple[Path, str]:
        prompt_dir = Path(__file__).resolve().parents[4] / "runtime" / "hermes-prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_name = run_id or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        prompt_path = prompt_dir / f"{prompt_name}.txt"
        prompt_path.write_text(question, encoding="utf-8")
        drive = prompt_path.drive.rstrip(":").lower()
        rest = prompt_path.as_posix().split(":", 1)[1].lstrip("/")
        wsl_path = f"/mnt/{drive}/{rest}" if drive else prompt_path.as_posix()
        return prompt_path, wsl_path

    def _build_chat_command(
        self,
        question: str,
        *,
        session_id: Optional[str] = None,
        toolsets: Optional[str] = None,
        skills: Optional[str] = None,
        model: Optional[str] = None,
        quiet: bool = True,
        quiet_query: bool = False,
        use_pty: bool = False,
        run_id: Optional[str] = None,
    ) -> str:
        prompt_path, wsl_prompt_path = self._prompt_file_path(question, run_id)
        args = [
            self.hermes_path,
            "chat",
            "-q",
            f"$(cat {shlex.quote(wsl_prompt_path)})",
        ]

        if session_id:
            args.extend(["--resume", session_id])
        if toolsets:
            args.extend(["-t", toolsets])
        if skills:
            args.extend(["-s", skills])
        if model:
            args.extend(["-m", model])
        if quiet_query:
            args.append("-Q")

        env = dict(self._env)
        if not quiet:
            env.pop("HERMES_QUIET", None)
        env_str = " ".join(f"{key}={shlex.quote(value)}" for key, value in env.items())
        quoted_args = []
        for index, arg in enumerate(args):
            if index >= 3 and args[index - 1] == "-q":
                quoted_args.append(f'"{arg}"')
            else:
                quoted_args.append(shlex.quote(arg))
        command = f"{env_str} {' '.join(quoted_args)}".strip()
        if use_pty:
            command = f"script -q -e -c {shlex.quote(command)} /dev/null"
        logger.info("Hermes prompt file: %s", prompt_path)
        return f"wsl -d {shlex.quote(self.wsl_distribution)} -- bash -lc {shlex.quote(command)}"

    @staticmethod
    def _clean_line(line: str) -> str:
        return ANSI_RE.sub("", line).replace("\r", "").strip()

    @staticmethod
    def _is_box_line(line: str) -> bool:
        return bool(line) and ord(line[0]) in BOX_CODEPOINTS

    @staticmethod
    def _strip_box_edges(line: str) -> str:
        chars = line.strip()
        while chars and ord(chars[0]) in BOX_CODEPOINTS:
            chars = chars[1:].strip()
        while chars and ord(chars[-1]) in BOX_CODEPOINTS:
            chars = chars[:-1].strip()
        return chars

    @staticmethod
    def _is_footer_or_noise(line: str) -> bool:
        lower = line.lower()
        markers = [
            "available tools",
            "duration:",
            "hermes --resume",
            "messages:",
            "resume this session",
            "session:",
            "query:",
        ]
        return any(marker in lower for marker in markers)

    @staticmethod
    def _normalize_artifact_path(path: str) -> str:
        cleaned = path.strip().strip(".,;:)]}\"'")
        match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", cleaned)
        if match:
            drive = match.group(1).upper()
            rest = match.group(2).replace("/", "\\")
            return f"{drive}:\\{rest}"
        return cleaned

    @staticmethod
    def _artifact_type_from_path(path: str) -> str:
        suffix = Path(path).suffix.lower()
        if suffix == ".md":
            return "markdown_report"
        if suffix in {".html", ".htm"}:
            return "html_page"
        if suffix == ".pptx":
            return "ppt_deck"
        if suffix in {".png", ".jpg", ".jpeg"}:
            return "image_result"
        if suffix in {".csv", ".xlsx"}:
            return "data_table"
        return "file"

    @staticmethod
    def _source_dir_from_path(path: str) -> str:
        if re.match(r"^[A-Za-z]:\\", path):
            return str(PureWindowsPath(path).parent)
        return str(PurePosixPath(path.replace("\\", "/")).parent)

    def _remember_artifact_paths(self, text: str) -> None:
        cleaned_text = ANSI_RE.sub("", text).replace("\r", "\n")
        for match in ARTIFACT_PATH_RE.finditer(cleaned_text):
            path = self._normalize_artifact_path(match.group("path"))
            if path not in self.last_artifact_paths:
                self.last_artifact_paths.append(path)
                self.last_artifacts.append(
                    {
                        "artifact_path": path,
                        "artifact_type": self._artifact_type_from_path(path),
                        "run_id": None,
                        "source_dir": self._source_dir_from_path(path),
                    }
                )

    def _build_stream_event(
        self,
        *,
        content: str,
        raw_log_path: Path | None,
        run_id: Optional[str],
        completion_detected: bool,
        payload: dict[str, object] | None = None,
    ) -> HermesStreamEvent:
        artifacts: list[dict[str, str | None]] = []
        for item in self.last_artifacts:
            artifact = dict(item)
            if run_id and not artifact.get("run_id"):
                artifact["run_id"] = run_id
            artifacts.append(artifact)

        event_type = "completion_signal" if completion_detected else "stage_update"
        return HermesStreamEvent(
            event_type=event_type,
            content=content,
            artifact_paths=list(self.last_artifact_paths),
            artifacts=artifacts,
            raw_log_path=str(raw_log_path) if raw_log_path else None,
            completion_detected=completion_detected,
            payload=payload or {},
        )

    async def _terminate_process_tree(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        if process.returncode is not None:
            return

        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.communicate()
        else:
            process.terminate()

        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    async def cancel_run(self, run_id: str) -> bool:
        process = self.active_processes.get(run_id)
        if process is None:
            return False

        logger.info("Cancelling Hermes CLI process for run_id=%s", run_id)
        self.cancelled_run_ids.add(run_id)
        await self._terminate_process_tree(process)
        return True

    @staticmethod
    def _is_completion_signal(text: str) -> bool:
        normalized = re.sub(r"\s+", "", text.lower())
        completion_markers = [
            "\u62a5\u544a\u5df2\u5b8c\u6210",
            "\u62a5\u544a\u5df2\u751f\u6210",
            "\u4efb\u52a1\u5df2\u5b8c\u6210",
            "\u4efb\u52a1\u5b8c\u6210",
            "\u6700\u7ec8\u62a5\u544a\u5df2\u5b8c\u6210",
            "\u6700\u7ec8\u62a5\u544a\u5df2\u751f\u6210",
            "\u5df2\u751f\u6210\u6700\u7ec8\u62a5\u544a",
            "pptx\u8f6c\u6362\u5b8c\u6210",
            "ppt\u5df2\u751f\u6210",
            "\u8f6c\u6362\u5b8c\u6210",
            "finalreportcompleted",
            "reportcompleted",
        ]
        return any(marker in normalized for marker in completion_markers)

    @staticmethod
    def _should_emit_box(text: str) -> bool:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return False

        lower = text.lower()
        noisy_markers = [
            "mcp servers",
            "toolset",
            "toolsets",
            "browser:",
            "code_execution:",
            "delegation:",
            "homeassistant:",
            "(and ",
        ]
        if any(marker in lower for marker in noisy_markers):
            return False

        if len(lines) > 4:
            return False

        return True

    def _extract_hermes_box_text(self, line: str) -> tuple[bool, str | None]:
        cleaned = self._clean_line(line)
        if not cleaned:
            return False, None

        if self._is_footer_or_noise(cleaned):
            return False, None

        if self._is_box_line(cleaned) and "Hermes" in cleaned:
            return True, None

        if self._is_box_line(cleaned):
            text = self._strip_box_edges(cleaned)
            if not text or "Hermes" in text:
                return False, None
            return False, text

        return False, None

    async def ask(
        self,
        question: str,
        session_id: Optional[str] = None,
        toolsets: Optional[str] = None,
        skills: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Tuple[str, str]:
        process = await asyncio.create_subprocess_shell(
            self._build_chat_command(
                question,
                session_id=session_id,
                toolsets=toolsets,
                skills=skills,
                model=model,
                quiet_query=True,
            ),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()
        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()
        self.last_artifact_paths = []
        self.last_artifacts = []
        self._remember_artifact_paths(stdout_str)
        self._remember_artifact_paths(stderr_str)
        self.last_diagnostics = {
            "artifact_paths": list(self.last_artifact_paths),
            "artifacts": list(self.last_artifacts),
            "exit_code": process.returncode,
            "last_stage": None,
            "stderr_tail": stderr_str[-2000:],
            "stdout_tail": stdout_str[-2000:],
        }

        if process.returncode != 0:
            error_msg = stderr_str or f"Hermes exited with code {process.returncode}"
            raise RuntimeError(f"Hermes CLI error: {error_msg}")

        return self._parse_output(stdout_str)

    async def ask_stream(
        self,
        question: str,
        session_id: Optional[str] = None,
        toolsets: Optional[str] = None,
        skills: Optional[str] = None,
        model: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        async for event in self.ask_stream_events(
            question=question,
            session_id=session_id,
            toolsets=toolsets,
            skills=skills,
            model=model,
            run_id=run_id,
        ):
            content = event.content.strip()
            if content:
                yield content

    async def ask_stream_events(
        self,
        question: str,
        session_id: Optional[str] = None,
        toolsets: Optional[str] = None,
        skills: Optional[str] = None,
        model: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> AsyncGenerator[HermesStreamEvent, None]:
        self.last_artifact_paths = []
        self.last_artifacts = []
        self.last_diagnostics = {
            "artifact_paths": [],
            "artifacts": [],
            "exit_code": None,
            "last_stage": None,
            "raw_log_path": None,
            "stderr_tail": "",
            "stdout_tail": "",
        }

        logger.info(
            "Starting Hermes stream: question_chars=%s session_id=%s toolsets=%s skills=%s model=%s",
            len(question),
            session_id or "",
            toolsets or "",
            skills or "",
            model or "",
        )
        raw_log_path = self._raw_log_path()
        self.last_diagnostics["raw_log_path"] = str(raw_log_path)
        raw_log_path.write_text(
            (
                "Hermes raw stream log\n"
                f"started_at={datetime.now().isoformat()}\n"
                f"question_chars={len(question)} session_id={session_id or ''} "
                f"toolsets={toolsets or ''} skills={skills or ''} model={model or ''}\n\n"
            ),
            encoding="utf-8",
        )
        logger.info("Hermes raw output log: %s", raw_log_path)

        process = await asyncio.create_subprocess_shell(
            self._build_chat_command(
                question,
                session_id=session_id,
                toolsets=toolsets,
                skills=skills,
                model=model,
                quiet=False,
                use_pty=True,
                run_id=run_id,
            ),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if run_id:
            self.active_processes[run_id] = process

        in_hermes_box = False
        box_lines: list[str] = []
        emitted_output = False
        last_emitted = ""
        stdout_tail = ""
        stderr_tail = ""
        stderr_chunks: list[str] = []
        line_queue: asyncio.Queue[str | None] = asyncio.Queue()
        completion_detected = False

        async def stop_after_completion() -> None:
            if process.returncode is not None:
                return
            logger.info(
                "Hermes completion signal received; stopping CLI after grace period."
            )
            await self._terminate_process_tree(process)

        async def flush_box() -> str | None:
            text = "\n".join(line for line in box_lines if line).strip()
            box_lines.clear()
            if not text or not self._should_emit_box(text):
                return None
            return text

        def parse_box_line(raw_line: str) -> tuple[bool, bool, str | None]:
            cleaned = self._clean_line(raw_line)
            if not cleaned or self._is_footer_or_noise(cleaned):
                return False, False, None

            is_box_line = self._is_box_line(cleaned)
            if is_box_line and "Hermes" in cleaned:
                return True, True, None

            if is_box_line:
                text = self._strip_box_edges(cleaned)
                if not text or "Hermes" in text:
                    return True, False, None
                return True, False, text

            return False, False, cleaned

        async def read_stream(stream: asyncio.StreamReader | None, is_stderr: bool) -> None:
            nonlocal completion_detected, stderr_tail, stdout_tail

            if stream is None:
                await line_queue.put(None)
                return

            stream_pending = ""
            while True:
                chunk = await stream.read(1024)
                if not chunk:
                    break

                decoded = chunk.decode("utf-8", errors="replace")
                with raw_log_path.open("a", encoding="utf-8", errors="replace") as raw_log:
                    raw_log.write(("STDERR " if is_stderr else "STDOUT ") + decoded)
                self._remember_artifact_paths(decoded)
                if self._is_completion_signal(decoded):
                    completion_detected = True
                if is_stderr:
                    stderr_tail = (stderr_tail + decoded)[-4000:]
                else:
                    stdout_tail = (stdout_tail + decoded)[-4000:]
                if is_stderr:
                    stderr_chunks.append(decoded)

                stream_pending += decoded.replace("\r", "\n")
                lines = stream_pending.split("\n")
                stream_pending = lines.pop() if lines else ""

                for raw_line in lines:
                    await line_queue.put(raw_line)

            if stream_pending.strip():
                await line_queue.put(stream_pending)
            await line_queue.put(None)

        stream_tasks = [
            asyncio.create_task(read_stream(process.stdout, False)),
            asyncio.create_task(read_stream(process.stderr, True)),
        ]
        finished_streams = 0

        try:
            while finished_streams < len(stream_tasks):
                try:
                    raw_line = await asyncio.wait_for(
                        line_queue.get(),
                        timeout=8 if completion_detected else None,
                    )
                except asyncio.TimeoutError:
                    await stop_after_completion()
                    break

                if raw_line is None:
                    finished_streams += 1
                    continue

                is_box_line, starts_box, text = parse_box_line(raw_line)

                if starts_box:
                    if in_hermes_box:
                        flushed = await flush_box()
                        if flushed and flushed != last_emitted:
                            emitted_output = True
                            last_emitted = flushed
                            self.last_diagnostics["last_stage"] = flushed
                            completion_detected = self._is_completion_signal(flushed)
                            logger.info("Hermes stage emitted: %s", flushed[:500])
                            yield self._build_stream_event(
                                content=flushed,
                                raw_log_path=raw_log_path,
                                run_id=run_id,
                                completion_detected=completion_detected,
                            )
                    in_hermes_box = True
                    continue

                if in_hermes_box and text:
                    box_lines.append(text)
                    continue

                if in_hermes_box and is_box_line and box_lines:
                    flushed = await flush_box()
                    if flushed and flushed != last_emitted:
                        emitted_output = True
                        last_emitted = flushed
                        self.last_diagnostics["last_stage"] = flushed
                        completion_detected = self._is_completion_signal(flushed)
                        logger.info("Hermes stage emitted: %s", flushed[:500])
                        yield self._build_stream_event(
                            content=flushed,
                            raw_log_path=raw_log_path,
                            run_id=run_id,
                            completion_detected=completion_detected,
                        )
                    in_hermes_box = False
                    continue

                if in_hermes_box and is_box_line:
                    continue
        except asyncio.CancelledError:
            if run_id:
                self.cancelled_run_ids.add(run_id)
            await self._terminate_process_tree(process)
            raise

        if in_hermes_box:
            flushed = await flush_box()
            if flushed and flushed != last_emitted:
                emitted_output = True
                self.last_diagnostics["last_stage"] = flushed
                completion_detected = self._is_completion_signal(flushed)
                logger.info("Hermes stage emitted: %s", flushed[:500])
                yield self._build_stream_event(
                    content=flushed,
                    raw_log_path=raw_log_path,
                    run_id=run_id,
                    completion_detected=completion_detected,
                )

        if completion_detected:
            await stop_after_completion()

        try:
            await process.wait()
            await asyncio.gather(*stream_tasks)
            for artifact in self.last_artifacts:
                artifact["run_id"] = run_id
            self.last_diagnostics.update(
                {
                    "artifact_paths": list(self.last_artifact_paths),
                    "artifacts": list(self.last_artifacts),
                    "completion_detected": completion_detected,
                    "emitted_output": emitted_output,
                    "exit_code": process.returncode,
                    "last_stage": self.last_diagnostics.get("last_stage"),
                    "stderr_tail": stderr_tail[-2000:],
                    "stdout_tail": stdout_tail[-2000:],
                }
            )
            logger.info("Hermes stream process exited: returncode=%s", process.returncode)
        finally:
            if run_id and self.active_processes.get(run_id) is process:
                self.active_processes.pop(run_id, None)

        if run_id and run_id in self.cancelled_run_ids:
            self.cancelled_run_ids.discard(run_id)
            return

        if process.returncode != 0:
            stderr_str = "".join(stderr_chunks).strip()
            if completion_detected and emitted_output:
                logger.warning(
                    "Hermes process was stopped after a completion signal; treating as completed."
                )
                return
            if process.returncode == 134 and (emitted_output or self.last_artifact_paths):
                logger.warning(
                    "Hermes exited with code 134 after emitting output; treating as completed."
                )
                return

            diagnostic_tail = (stderr_tail or stdout_tail).strip()
            error_msg = diagnostic_tail or stderr_str or f"Hermes exited with code {process.returncode}"
            raise RuntimeError(f"Hermes CLI error: {error_msg}")

    def _parse_output(self, output: str) -> Tuple[str, str]:
        lines = output.split("\n")
        session_id = ""
        response_lines = []
        in_hermes_box = False
        box_lines: list[str] = []

        for line in lines:
            cleaned = self._clean_line(line)
            if cleaned.startswith("session_id:"):
                session_id = cleaned.split(":", 1)[1].strip()
                continue

            if not cleaned:
                continue

            if self._is_box_line(cleaned) and "Hermes" in cleaned:
                if in_hermes_box and box_lines:
                    text = "\n".join(box_lines).strip()
                    if text and self._should_emit_box(text):
                        response_lines.append(text)
                    box_lines.clear()
                in_hermes_box = True
                continue

            if in_hermes_box:
                if self._is_box_line(cleaned):
                    text = self._strip_box_edges(cleaned)
                    if text and "Hermes" not in text:
                        box_lines.append(text)
                    elif box_lines:
                        text = "\n".join(box_lines).strip()
                        if text and self._should_emit_box(text):
                            response_lines.append(text)
                        box_lines.clear()
                        in_hermes_box = False
                elif cleaned:
                    box_lines.append(cleaned)

        if in_hermes_box and box_lines:
            text = "\n".join(box_lines).strip()
            if text and self._should_emit_box(text):
                response_lines.append(text)

        response = "\n\n".join(line for line in response_lines if line).strip()
        return session_id, response

    async def list_toolsets(self) -> list[str]:
        process = await asyncio.create_subprocess_shell(
            self._build_wsl_command([self.hermes_path, "tools", "--summary", "list"]),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return []

        output = stdout.decode("utf-8", errors="replace")
        toolsets = []
        for line in output.split("\n"):
            cleaned = self._clean_line(line)
            match = re.match(r"^[^\w\s]?\s*(?:enabled|disabled)\s+([a-zA-Z0-9_\-:]+)\s+", cleaned)
            if match:
                toolsets.append(match.group(1))
        return toolsets

    async def list_skills(self) -> list[str]:
        process = await asyncio.create_subprocess_shell(
            self._build_wsl_command([self.hermes_path, "skills", "list"]),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return []

        output = stdout.decode("utf-8", errors="replace")
        skills = []
        for line in output.split("\n"):
            cleaned = self._clean_line(line)
            if not cleaned.startswith("|") and "|" not in cleaned:
                continue
            parts = [part.strip() for part in cleaned.strip("|").split("|")]
            if parts and parts[0] and parts[0] != "Name":
                skills.append(parts[0])
        return skills
