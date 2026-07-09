import asyncio
import re
import shlex
from typing import AsyncGenerator, Optional, Tuple


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
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

    def _build_wsl_command(self, args: list[str], quiet: bool = True) -> str:
        env = dict(self._env)
        if not quiet:
            env.pop("HERMES_QUIET", None)

        env_str = " ".join(f"{key}={shlex.quote(value)}" for key, value in env.items())
        quoted_args = " ".join(shlex.quote(arg) for arg in args)
        command = f"{env_str} {quoted_args}".strip()
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
        args = [self.hermes_path, "chat", "-q", question, "-Q"]

        if session_id:
            args.extend(["--resume", session_id])
        if toolsets:
            args.extend(["-t", toolsets])
        if skills:
            args.extend(["-s", skills])
        if model:
            args.extend(["-m", model])

        process = await asyncio.create_subprocess_shell(
            self._build_wsl_command(args),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()
        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()

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
    ) -> AsyncGenerator[str, None]:
        args = [self.hermes_path, "chat", "-q", question]

        if session_id:
            args.extend(["--resume", session_id])
        if toolsets:
            args.extend(["-t", toolsets])
        if skills:
            args.extend(["-s", skills])
        if model:
            args.extend(["-m", model])

        process = await asyncio.create_subprocess_shell(
            self._build_wsl_command(args, quiet=False),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stderr_chunks: list[str] = []

        async def read_stderr() -> None:
            if process.stderr is None:
                return
            while True:
                chunk = await process.stderr.read(1024)
                if not chunk:
                    break
                stderr_chunks.append(chunk.decode("utf-8", errors="replace"))

        stderr_task = asyncio.create_task(read_stderr())

        pending = ""
        in_hermes_box = False
        box_lines: list[str] = []
        last_emitted = ""

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

            return False, False, None

        if process.stdout is not None:
            while True:
                chunk = await process.stdout.read(1024)
                if not chunk:
                    break

                pending += chunk.decode("utf-8", errors="replace")
                lines = pending.split("\n")
                pending = lines.pop() if lines else ""

                for raw_line in lines:
                    is_box_line, starts_box, text = parse_box_line(raw_line)

                    if starts_box:
                        if in_hermes_box:
                            flushed = await flush_box()
                            if flushed and flushed != last_emitted:
                                last_emitted = flushed
                                yield flushed
                        in_hermes_box = True
                        continue

                    if in_hermes_box and text:
                        box_lines.append(text)
                        continue

                    if in_hermes_box and is_box_line and box_lines:
                        flushed = await flush_box()
                        if flushed and flushed != last_emitted:
                            last_emitted = flushed
                            yield flushed
                        in_hermes_box = False
                        continue

                    if in_hermes_box and is_box_line:
                        continue

        if pending.strip():
            _, _, text = parse_box_line(pending)
            if in_hermes_box and text:
                box_lines.append(text)

        if in_hermes_box:
            flushed = await flush_box()
            if flushed and flushed != last_emitted:
                yield flushed

        await process.wait()
        await stderr_task

        if process.returncode != 0:
            stderr_str = "".join(stderr_chunks).strip()
            error_msg = stderr_str or f"Hermes exited with code {process.returncode}"
            raise RuntimeError(f"Hermes CLI error: {error_msg}")

    def _parse_output(self, output: str) -> Tuple[str, str]:
        lines = output.split("\n")
        session_id = ""
        response_lines = []

        for line in lines:
            cleaned = self._clean_line(line)
            if cleaned.startswith("session_id:"):
                session_id = cleaned.split(":", 1)[1].strip()
            elif cleaned:
                response_lines.append(cleaned)

        response = "\n".join(response_lines).strip()
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
