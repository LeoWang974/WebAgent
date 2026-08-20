# File purpose: Implements the Hermes CLI integration for cli.
# Main declarations: HermesStreamEvent defines hermes stream event state or behavior;
# HermesCliWrapper defines hermes cli wrapper state or behavior.

import asyncio
import codecs
import json
import logging
import os
import re
import shlex
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from app.core.config import settings
from app.schemas.artifact import ArtifactType
from app.schemas.artifact_manifest import ARTIFACT_MANIFEST_SCHEMA
from app.services.artifact_manifest import (
    ARTIFACT_MANIFEST_FILENAME,
    ArtifactManifestRecorder,
)
from app.services.run_artifact_watcher import (
    ArtifactFileTransition,
    RunArtifactWatcher,
)

from .process_registry import (
    register_run_process,
    terminate_processes_by_marker,
    terminate_registered_run_process,
    unregister_run_process,
)

logger = logging.getLogger(__name__)

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
ARTIFACT_PATH_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:\\|/mnt/[a-zA-Z]/|/home/|/tmp/)[^\"'<>|`\r\n]+?\.(?:md|html?|pptx|png|jpe?g|csv|xlsx|json))",
    re.IGNORECASE,
)
FINAL_ARTIFACT_NAME_RE = re.compile(
    r"(?P<path>[^\"'<>|`\r\n:：]*?\.(?:md|html?|pptx|png|jpe?g|csv|xlsx|json))",
    re.IGNORECASE,
)
ARTIFACT_SUFFIXES = {
    ".md",
    ".html",
    ".htm",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".csv",
    ".xlsx",
    ".json",
}
IGNORED_ARTIFACT_PATH_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "site-packages",
}
IGNORED_ARTIFACT_PATH_SUFFIXES = (".dist-info", ".egg-info")
IGNORED_ARTIFACT_FILENAMES = {
    ARTIFACT_MANIFEST_FILENAME,
    "package-lock.json",
    "package.json",
    "readme.md",
    "request.md",
    "skill.md",
    "soul.md",
    "testing.md",
}
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
MOJIBAKE_BOX_PREFIXES = ("\u923a", "\u9239", "\u923a\ue75b", "\u923a\ue75b\u6522")


@dataclass(frozen=True)
class HermesStreamEvent:
    event_type: str
    content: str
    artifact_paths: list[str] = field(default_factory=list)
    artifacts: list[dict[str, object]] = field(default_factory=list)
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
        hermes_path: str = "hermes",
        hermes_home: str = "~/.hermes",
        wsl_distribution: str = "Ubuntu",
        serper_configured: bool = False,
    ):
        self.hermes_path = hermes_path
        normalized_home = hermes_home.replace("\\", "/")
        self.hermes_home = (
            normalized_home
            if normalized_home.startswith("/")
            else Path(hermes_home).expanduser().as_posix()
        )
        self.wsl_distribution = wsl_distribution
        self._env = {
            "HERMES_HOME": self.hermes_home,
            "HERMES_QUIET": "1",
            "HOME": self.hermes_home,
            "SEARCH_PROVIDER": os.getenv("SEARCH_PROVIDER", "serper"),
            "WEBAGENT_SEARCH_PROVIDER": os.getenv("SEARCH_PROVIDER", "serper"),
            "WEBAGENT_SERPER_CONFIGURED": (
                "1" if serper_configured or os.getenv("SERPER_API_KEY") else "0"
            ),
        }
        self.auto_approve_commands = os.getenv("WEBAGENT_HERMES_YOLO", "1").lower() not in {
            "0",
            "false",
            "no",
        }
        self.last_artifact_paths: list[str] = []
        self.last_artifacts: list[dict[str, object]] = []
        self.last_diagnostics: dict[str, object] = {}
        self.artifact_manifest_recorder: ArtifactManifestRecorder | None = None
        self.artifact_watcher: RunArtifactWatcher | None = None
        self.stream_started_at: datetime | None = None
        self.active_processes: dict[str, asyncio.subprocess.Process] = {}
        self.cancelled_run_ids: set[str] = set()

    @staticmethod
    def _bash_exec_args(command: str) -> list[str]:
        return ["bash", "--noprofile", "--norc", "-c", command]

    def _with_runtime_env(self, command: str) -> str:
        env_path = PurePosixPath(self.hermes_home) / ".env"
        env_loader = (
            f"for __f in ~/.hermes/.env {shlex.quote(str(env_path))}; do "
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
        )
        return env_loader + command

    def _raw_log_path(self, run_id: str | None = None) -> Path:
        log_dir = Path(__file__).resolve().parents[4] / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        run_suffix = re.sub(r"[^A-Za-z0-9_-]+", "-", run_id or "run")[:32]
        return log_dir / f"hermes-raw-{timestamp}-{run_suffix}.log"

    def _prompt_file_path(self, question: str, run_id: str | None = None) -> tuple[Path, str]:
        prompt_dir = Path(__file__).resolve().parents[4] / "runtime" / "hermes-prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_name = run_id or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        prompt_path = prompt_dir / f"{prompt_name}.txt"
        prompt_path.write_text(question, encoding="utf-8")
        drive = prompt_path.drive.rstrip(":").lower()
        if drive:
            rest = prompt_path.as_posix().split(":", 1)[1].lstrip("/")
            wsl_path = f"/mnt/{drive}/{rest}"
        else:
            wsl_path = prompt_path.as_posix()
        return prompt_path, wsl_path

    @staticmethod
    def _shell_visible_path(path_value: str) -> str:
        path = Path(path_value).expanduser()
        drive = path.drive.rstrip(":").lower()
        if drive:
            rest = path.as_posix().split(":", 1)[1].lstrip("/")
            return f"/mnt/{drive}/{rest}"
        return path.as_posix()

    @staticmethod
    def _host_visible_path(path_value: str) -> Path:
        normalized = path_value.replace("\\", "/")
        match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", normalized)
        if os.name == "nt" and match:
            drive, remainder = match.groups()
            return Path(f"{drive.upper()}:/{remainder}")
        return Path(path_value).expanduser()

    def _recover_latest_session_assistant_content(
        self,
        *,
        started_at: datetime,
    ) -> str | None:
        sessions_dir = self._host_visible_path(self.hermes_home) / "sessions"
        if not sessions_dir.is_dir():
            return None

        started_timestamp = started_at.timestamp() - 5
        candidates = sorted(
            (
                path
                for path in sessions_dir.glob("session_*.json")
                if path.is_file() and path.stat().st_mtime >= started_timestamp
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in candidates:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                logger.debug("Unable to read Hermes session output: %s", path, exc_info=True)
                continue
            messages = payload.get("messages")
            if not isinstance(messages, list):
                continue
            for message in reversed(messages):
                if not isinstance(message, dict) or message.get("role") != "assistant":
                    continue
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
        return None

    def _session_message_counts(self) -> dict[Path, int]:
        """Capture message cursors before a resumed Hermes process starts."""

        sessions_dir = self._host_visible_path(self.hermes_home) / "sessions"
        if not sessions_dir.is_dir():
            return {}

        counts: dict[Path, int] = {}
        for path in sessions_dir.glob("session_*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            messages = payload.get("messages")
            if isinstance(messages, list):
                counts[path.resolve()] = len(messages)
        return counts

    @staticmethod
    def _iter_session_text(value: object) -> list[str]:
        texts: list[str] = []
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                texts.extend(HermesCliWrapper._iter_session_text(item))
        elif isinstance(value, list):
            for item in value:
                texts.extend(HermesCliWrapper._iter_session_text(item))
        return texts

    def _recover_session_updates(
        self,
        *,
        started_at: datetime,
        message_cursors: dict[Path, int],
    ) -> tuple[list[str], list[str]]:
        """Read only messages appended by the current Run from Hermes session files."""

        sessions_dir = self._host_visible_path(self.hermes_home) / "sessions"
        if not sessions_dir.is_dir():
            return [], []

        started_timestamp = started_at.timestamp() - 5
        assistant_updates: list[str] = []
        artifact_paths: list[str] = []
        for path in sorted(sessions_dir.glob("session_*.json"), key=lambda item: str(item)):
            try:
                resolved_path = path.resolve()
                if path.stat().st_mtime < started_timestamp:
                    continue
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                logger.debug("Unable to read Hermes session update: %s", path, exc_info=True)
                continue
            messages = payload.get("messages")
            if not isinstance(messages, list):
                continue
            start_index = min(message_cursors.get(resolved_path, 0), len(messages))
            new_messages = messages[start_index:]
            message_cursors[resolved_path] = len(messages)
            for message in new_messages:
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if (
                    message.get("role") == "assistant"
                    and isinstance(content, str)
                    and content.strip()
                ):
                    assistant_updates.append(content.strip())
                for text in self._iter_session_text(message):
                    for match in ARTIFACT_PATH_RE.finditer(text):
                        candidate = self._normalize_artifact_path(match.group("path"))
                        if candidate not in artifact_paths:
                            artifact_paths.append(candidate)
        return assistant_updates, artifact_paths

    @staticmethod
    def _is_primary_completion_artifact(path: Path) -> bool:
        """Exclude planning files and slide fragments from early Run completion."""

        suffix = path.suffix.lower()
        if suffix not in {".md", ".htm", ".html", ".pptx"}:
            return False
        lower_parts = {part.lower() for part in path.parts}
        if lower_parts.intersection({"sub_reports", "sub-reports", "pages", "slides"}):
            return False
        lower_name = path.name.lower()
        if lower_name in {
            "briefing.md",
            "request.md",
            "synthesis.md",
            "task.md",
        }:
            return False
        if suffix in {".htm", ".html"} and lower_name.startswith("page_"):
            return False
        return True

    def _build_chat_exec_args(
        self,
        question: str,
        *,
        session_id: str | None = None,
        quiet: bool = True,
        quiet_query: bool = False,
        use_pty: bool = False,
        run_id: str | None = None,
    ) -> list[str]:
        command = self._build_chat_bash_command(
            question,
            session_id=session_id,
            quiet=quiet,
            quiet_query=quiet_query,
            use_pty=use_pty,
            run_id=run_id,
        )
        if os.name != "nt":
            return self._bash_exec_args(command)
        return [
            "wsl.exe",
            "-d",
            self.wsl_distribution,
            "--",
            "bash",
            "--noprofile",
            "--norc",
            "-c",
            command,
        ]

    def _build_chat_bash_command(
        self,
        question: str,
        *,
        session_id: str | None = None,
        quiet: bool = True,
        quiet_query: bool = False,
        use_pty: bool = False,
        run_id: str | None = None,
    ) -> str:
        prompt_path, wsl_prompt_path = self._prompt_file_path(question, run_id)
        pre_prompt_args = [
            self.hermes_path,
            *(["--yolo"] if self.auto_approve_commands else []),
            "chat",
            "-q",
        ]
        post_prompt_args: list[str] = []

        if session_id:
            post_prompt_args.extend(["--resume", session_id])
        if quiet_query:
            post_prompt_args.append("-Q")

        python_code = (
            "import json, subprocess, sys\n"
            f"__prompt_path = {json.dumps(wsl_prompt_path, ensure_ascii=False)}\n"
            f"__pre = {json.dumps(pre_prompt_args, ensure_ascii=False)}\n"
            f"__post = {json.dumps(post_prompt_args, ensure_ascii=False)}\n"
            "with open(__prompt_path, 'r', encoding='utf-8') as __f:\n"
            "    __prompt = __f.read()\n"
            "sys.exit(subprocess.call([*__pre, __prompt, *__post]))\n"
        )

        env = dict(self._env)
        if not quiet:
            env.pop("HERMES_QUIET", None)
        env_str = " ".join(f"{key}={shlex.quote(value)}" for key, value in env.items())
        command = self._with_runtime_env(
            f"{env_str} python3 -c {shlex.quote(python_code)}".strip()
        )
        workspace = env.get("WEBAGENT_RUN_WORKSPACE")
        if workspace:
            command = f"cd {shlex.quote(workspace)} && {command}"
        if use_pty:
            command = f"script -q -e -c {shlex.quote(command)} /dev/null"
        logger.info("Hermes prompt file: %s", prompt_path)
        return command

    @staticmethod
    def _clean_line(line: str) -> str:
        cleaned = ANSI_RE.sub("", line).replace("\r", "").strip()
        return HermesCliWrapper._repair_mojibake_text(cleaned)

    @staticmethod
    def _repair_mojibake_text(text: str) -> str:
        if not text or text.isascii():
            return text
        try:
            repaired = text.encode("gb18030").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return text
        has_visible_unicode = any(
            "\u3400" <= char <= "\u9fff" or ord(char) in BOX_CODEPOINTS
            for char in repaired
        )
        return repaired if repaired != text and has_visible_unicode else text

    @staticmethod
    def _is_box_line(line: str) -> bool:
        return bool(line) and (
            ord(line[0]) in BOX_CODEPOINTS or line.startswith(MOJIBAKE_BOX_PREFIXES)
        )

    @staticmethod
    def _strip_box_edges(line: str) -> str:
        chars = line.strip()
        while chars and ord(chars[0]) in BOX_CODEPOINTS:
            chars = chars[1:].strip()
        while chars.startswith(MOJIBAKE_BOX_PREFIXES):
            for prefix in MOJIBAKE_BOX_PREFIXES:
                if chars.startswith(prefix):
                    chars = chars[len(prefix) :].strip()
                    break
        while chars.startswith("?"):
            chars = chars[1:].strip()
        while chars and ord(chars[-1]) in BOX_CODEPOINTS:
            chars = chars[:-1].strip()
        while chars.endswith(MOJIBAKE_BOX_PREFIXES):
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
    def _artifact_type_from_path(path: str) -> ArtifactType | None:
        artifact_types: dict[str, ArtifactType] = {
            ".md": "markdown_report",
            ".html": "html_page",
            ".htm": "html_page",
            ".pptx": "ppt_deck",
            ".png": "image_result",
            ".jpg": "image_result",
            ".jpeg": "image_result",
            ".csv": "data_table",
            ".xlsx": "data_table",
            ".json": "debug_json",
        }
        return artifact_types.get(Path(path).suffix.lower())

    @staticmethod
    def _source_dir_from_path(path: str) -> str:
        if re.match(r"^[A-Za-z]:\\", path):
            return str(PureWindowsPath(path).parent)
        return str(PurePosixPath(path.replace("\\", "/")).parent)

    def _artifact_host_path(self, path: str) -> Path:
        normalized = path.replace("\\", "/")
        if os.name == "nt" and normalized.startswith("/home/"):
            distro = self.wsl_distribution.strip() or "Ubuntu"
            return Path(f"\\\\wsl.localhost\\{distro}") / normalized.lstrip("/").replace(
                "/", "\\"
            )
        return self._host_visible_path(path)

    @staticmethod
    def _manifest_artifact_role(path: str, artifact_type: str) -> str:
        normalized = path.replace("\\", "/").lower()
        filename = PurePosixPath(normalized).name
        if artifact_type == "debug_json":
            return "intermediate"
        if artifact_type == "html_page" and "/pages/" in normalized and filename.startswith(
            "page_"
        ):
            return "preview_fallback"
        return "primary"

    def _remember_artifact_path(
        self,
        path: str,
        *,
        discovered_by: str = "terminal_output",
        status: str = "ready",
        size_bytes: int | None = None,
        mtime_ns: int | None = None,
        stable_at: datetime | None = None,
        error: str | None = None,
    ) -> bool:
        artifact_type = self._artifact_type_from_path(path)
        if artifact_type is None:
            logger.debug("Ignoring unsupported artifact path: %s", path)
            return False
        host_path = self._artifact_host_path(path)
        if (
            self.stream_started_at is not None
            and status == "ready"
            and discovered_by == "terminal_output"
        ):
            try:
                file_stat = host_path.stat()
            except OSError:
                return False
            if file_stat.st_mtime < self.stream_started_at.timestamp() - 5:
                logger.debug("Ignoring stale artifact path from Hermes output: %s", path)
                return False
        if (
            status == "ready"
            and discovered_by != "file_watcher"
            and self.artifact_watcher is not None
            and host_path.expanduser().resolve().is_relative_to(self.artifact_watcher.root)
        ):
            # Managed run outputs are authoritative only after the watcher has
            # observed a stable size and mtime window.
            self.artifact_watcher.track(host_path)
            return False
        is_new = path not in self.last_artifact_paths
        if status == "ready" and is_new:
            self.last_artifact_paths.append(path)

        source_dir = self._source_dir_from_path(path)
        item: dict[str, object] = {
            "artifact_path": path,
            "artifact_type": artifact_type,
            "run_id": None,
            "source_dir": source_dir,
            "title": PurePosixPath(path.replace("\\", "/")).stem,
            "status": status,
        }
        if self.artifact_manifest_recorder is not None:
            entry = self.artifact_manifest_recorder.record(
                path=path,
                artifact_type=artifact_type,
                title=str(item["title"]),
                role=self._manifest_artifact_role(path, artifact_type),
                discovered_by=discovered_by,
                source_dir=source_dir,
                source_file=host_path if status == "ready" and host_path.is_file() else None,
                status=status,
                size_bytes=size_bytes,
                mtime_ns=mtime_ns,
                stable_at=stable_at,
                error=error,
            )
            item.update(
                {
                    "entry_id": entry.entry_id,
                    "role": entry.role,
                    "status": entry.status,
                    "discovered_by": entry.discovered_by,
                    "path_scope": entry.path_scope,
                    "size_bytes": entry.size_bytes,
                    "sha256": entry.sha256,
                    "manifest_schema": ARTIFACT_MANIFEST_SCHEMA,
                }
            )
            status = entry.status
            item["status"] = status
            if status != "ready" and path in self.last_artifact_paths:
                self.last_artifact_paths.remove(path)

        existing_index = next(
            (
                index
                for index, existing in enumerate(self.last_artifacts)
                if existing.get("artifact_path") == path
            ),
            None,
        )
        if existing_index is None:
            self.last_artifacts.append(item)
        else:
            self.last_artifacts[existing_index] = item
        return status == "ready" and is_new

    def _remember_artifact_paths(self, text: str) -> None:
        cleaned_text = ANSI_RE.sub("", text).replace("\r", "\n")
        for match in ARTIFACT_PATH_RE.finditer(cleaned_text):
            path = self._normalize_artifact_path(match.group("path"))
            self._remember_artifact_path(path)

    def _final_artifact_search_roots(
        self,
        working_dir: str | None,
        artifacts_dir: str | None,
    ) -> list[Path]:
        roots: list[Path] = []
        hermes_home = self._host_visible_path(self.hermes_home)
        run_runtime_root = hermes_home.parent if hermes_home.name == "hermes-home" else None
        candidates = [
            artifacts_dir,
            working_dir,
            str(run_runtime_root) if run_runtime_root else None,
            str(Path.cwd()),
            str(Path(__file__).resolve().parents[4]),
            str(Path(__file__).resolve().parents[4] / "services" / "api"),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate).expanduser()
            if path.exists() and path not in roots:
                roots.append(path)
        return roots

    def _remember_final_output_artifact_paths(
        self,
        text: str,
        *,
        working_dir: str | None,
        artifacts_dir: str | None,
    ) -> None:
        """Resolve relative artifact names that Hermes reports in its final message."""

        self._remember_artifact_paths(text)
        roots = self._final_artifact_search_roots(working_dir, artifacts_dir)
        cleaned_text = ANSI_RE.sub("", text).replace("\r", "\n")
        for line in cleaned_text.splitlines():
            for match in FINAL_ARTIFACT_NAME_RE.finditer(line):
                candidate = match.group("path").strip().strip(".,;:：()[]{} ")
                if not candidate or ARTIFACT_PATH_RE.fullmatch(candidate):
                    continue
                relative_marker = max(candidate.rfind("./"), candidate.rfind(".\\"))
                if relative_marker >= 0:
                    candidate = candidate[relative_marker:]
                candidate_path = Path(candidate.replace("\\", os.sep).replace("/", os.sep))
                if candidate_path.name.lower() in IGNORED_ARTIFACT_FILENAMES:
                    continue
                if candidate_path.is_absolute():
                    if candidate_path.exists():
                        self._remember_artifact_path(str(candidate_path.resolve()))
                    continue
                for root in roots:
                    resolved = (root / candidate_path).resolve()
                    if resolved.is_file():
                        self._remember_artifact_path(str(resolved))
                        break

    def _discover_run_directory_artifacts(
        self,
        *,
        working_dir: str | None,
        artifacts_dir: str | None,
        started_at: datetime,
        failed_paths: set[Path] | None = None,
    ) -> None:
        """Perform a final, run-scoped filesystem discovery after Hermes exits."""

        roots: list[Path] = []
        hermes_home = self._host_visible_path(self.hermes_home)
        run_runtime_root = hermes_home.parent if hermes_home.name == "hermes-home" else None
        for candidate in (
            artifacts_dir,
            working_dir,
            str(run_runtime_root) if run_runtime_root else None,
        ):
            if not candidate:
                continue
            root = Path(candidate).expanduser()
            if root.exists() and root not in roots:
                roots.append(root)

        # A terminal-declared artifact may live outside the managed run root.
        # Its containing directory is a bounded recovery scope for sibling
        # outputs such as PPTX plus HTML slide fallbacks.
        for artifact_path in tuple(self.last_artifact_paths):
            parent = self._artifact_host_path(artifact_path).parent
            if parent.is_dir() and parent not in roots:
                roots.append(parent)

        threshold = started_at.timestamp() - 2
        for root in roots:
            for candidate in root.rglob("*"):
                try:
                    if (
                        candidate.is_file()
                        and candidate.resolve() not in (failed_paths or set())
                        and candidate.suffix.lower() in ARTIFACT_SUFFIXES
                        and not self._is_runtime_dependency_path(candidate)
                        and candidate.stat().st_mtime >= threshold
                    ):
                        self._remember_artifact_path(
                            str(candidate.resolve()),
                            discovered_by="recovery_scan",
                        )
                except OSError:
                    continue

    @staticmethod
    def _is_runtime_dependency_path(path: Path) -> bool:
        normalized_parts = tuple(part.lower() for part in path.parts)
        if path.name.lower() in IGNORED_ARTIFACT_FILENAMES:
            return True
        if any(part in IGNORED_ARTIFACT_PATH_PARTS for part in normalized_parts):
            return True
        if any(
            part.endswith(IGNORED_ARTIFACT_PATH_SUFFIXES)
            for part in normalized_parts
        ):
            return True
        if "hermes-home" in normalized_parts:
            hermes_index = normalized_parts.index("hermes-home")
            hermes_relative_parts = normalized_parts[hermes_index + 1 :]
            if not hermes_relative_parts or hermes_relative_parts[0] != "reports":
                return True
        return False

    @staticmethod
    def _summarize_raw_runtime_line(text: str) -> str | None:
        normalized = re.sub(r"\s+", " ", ANSI_RE.sub("", text)).strip()
        if not normalized:
            return None

        lower = normalized.lower()
        if re.search(r"\bpage[_-]?\d+\.(?:html?|png|jpe?g)\b", lower):
            match = re.search(r"page[_-]?(\d+)", lower)
            if match:
                return f"正在生成第 {int(match.group(1))} 页幻灯片..."
            return "正在生成幻灯片页面..."
        if "serper" in lower or "google.serper.dev" in lower:
            return "正在使用 Serper 搜索资料..."
        if "curl " in lower or (
            "http" in lower and any(word in lower for word in ("search", "fetch", "crawl"))
        ):
            return "正在抓取和整理网页资料..."
        if "read_file" in lower or re.search(r"\bread\s+", lower):
            return "正在读取相关文件..."
        if "write_file" in lower or re.search(r"\bwrite\s+", lower):
            return "正在写入中间文件..."
        if (
            "search_files" in lower
            or re.search(r"\bfind\s+", lower)
            or re.search(r"\bgrep\s+", lower)
        ):
            return "正在查找相关文件和产物..."
        if "run_stage.py" in lower and "export" in lower:
            return "正在导出 PPTX 文件..."
        if "html_to_pptx" in lower or "pptx" in lower and "export" in lower:
            return "正在转换并导出 PPTX..."
        if "outline.json" in lower:
            return "正在整理幻灯片大纲..."
        if "style_spec.json" in lower:
            return "正在生成幻灯片视觉规范..."
        if "task_pack.json" in lower or "info_pack.json" in lower:
            return "正在准备任务配置文件..."
        if "report.md" in lower or "final_report" in lower:
            return "正在处理 Markdown 报告..."
        return None

    def _build_stream_event(
        self,
        *,
        content: str,
        raw_log_path: Path | None,
        run_id: str | None,
        completion_detected: bool,
        artifact_found: bool = False,
        payload: dict[str, object] | None = None,
        event_type_override: str | None = None,
    ) -> HermesStreamEvent:
        artifacts: list[dict[str, object]] = []
        for item in self.last_artifacts:
            artifact = dict(item)
            if run_id and not artifact.get("run_id"):
                artifact["run_id"] = run_id
            artifacts.append(artifact)

        raw_event_type = "completion_signal" if completion_detected else "stage_update"
        event_type = event_type_override or self._classify_stream_event_type(
            content, completion_detected=completion_detected, artifact_found=artifact_found
        )
        event_payload: dict[str, object] = {
            "rawHermesEventType": raw_event_type,
            **(payload or {}),
        }
        if self.artifact_manifest_recorder is not None:
            event_payload.update(
                {
                    "artifactManifestPath": str(self.artifact_manifest_recorder.path),
                    "artifactManifestSchema": ARTIFACT_MANIFEST_SCHEMA,
                    "artifactManifestStatus": self.artifact_manifest_recorder.manifest.status,
                }
            )
        return HermesStreamEvent(
            event_type=event_type,
            content=content,
            artifact_paths=list(self.last_artifact_paths),
            artifacts=artifacts,
            raw_log_path=str(raw_log_path) if raw_log_path else None,
            completion_detected=completion_detected,
            payload=event_payload,
        )

    @staticmethod
    def _classify_stream_event_type(
        content: str,
        *,
        completion_detected: bool,
        artifact_found: bool = False,
    ) -> str:
        if completion_detected:
            return "completed"
        if artifact_found:
            return "artifact_found"

        normalized = content.lower()
        tool_markers = [
            "$ ",
            "exec",
            "read_file",
            "terminal",
            "python",
            "bash",
            "tool",
            "工具",
            "读取",
            "搜索",
            "调用",
            "转换",
            "写入",
            "下载",
        ]
        if any(marker in normalized for marker in tool_markers):
            return "tool_call"

        return "stage_started"

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
        except TimeoutError:
            process.kill()
            await process.wait()

    async def cancel_run(self, run_id: str) -> bool:
        self.cancelled_run_ids.add(run_id)
        process = self.active_processes.get(run_id)
        logger.info("Cancelling Hermes CLI process for run_id=%s", run_id)
        cancelled = False
        if process is not None:
            await self._terminate_process_tree(process)
            cancelled = True
        return await terminate_registered_run_process(run_id) or cancelled

    @staticmethod
    def _is_completion_signal(text: str) -> bool:
        # Hermes commonly wraps file extensions in Markdown backticks. Match
        # completion semantics independently of whitespace and punctuation so
        # a verified final artifact can close the run promptly.
        normalized = "".join(char for char in text.lower() if char.isalnum())
        completion_markers = [
            "duration",
            "\u62a5\u544a\u5df2\u5b8c\u6210",
            "\u62a5\u544a\u5df2\u751f\u6210",
            "\u62a5\u544a\u5b8c\u6210",
            "\u4efb\u52a1\u5df2\u5b8c\u6210",
            "\u4efb\u52a1\u5b8c\u6210",
            "\u6700\u7ec8\u62a5\u544a\u5df2\u5b8c\u6210",
            "\u6700\u7ec8\u62a5\u544a\u5df2\u751f\u6210",
            "\u5df2\u751f\u6210\u6700\u7ec8\u62a5\u544a",
            "pptx\u8f6c\u6362\u5b8c\u6210",
            "pptx\u5df2\u4fdd\u5b58",
            "pptx\u5df2\u751f\u6210",
            "pptxissaved",
            "pptxhasbeensaved",
            "pptxfilehasbeengeneratedandverified",
            "pptxhasbeengeneratedandverified",
            "htmlfilehasbeengeneratedandverified",
            "markdownreporthasbeengeneratedandverified",
            "ppt\u5df2\u751f\u6210",
            "\u8f6c\u6362\u5b8c\u6210",
            "finalreportcompleted",
            "reportcompleted",
            "resumethissessionwith:",
        ]
        return any(marker in normalized for marker in completion_markers)

    @staticmethod
    def _has_user_visible_signal(text: str) -> bool:
        normalized = text.strip()
        if not normalized:
            return False

        # Hermes may return a concise answer without punctuation (for example,
        # when the user asks it to reply with an exact phrase). Content inside
        # an explicit Hermes box is still user-visible output in that case.
        if sum("\u3400" <= char <= "\u9fff" for char in normalized) >= 2:
            return True

        lower = normalized.lower()
        content_markers = [
            "\u3002",
            "\uff1f",
            "\uff01",
            "\uff1a",
            "\u641c\u7d22",
            "\u6293\u53d6",
            "\u89c4\u5212",
            "\u5199\u4f5c",
            "\u9a8c\u8bc1",
            "\u5bfc\u51fa",
            "\u751f\u6210",
            "\u5b8c\u6210",
            "\u62a5\u544a",
            "\u4ea7\u7269",
            "stage",
            "search",
            "fetch",
            "crawl",
            "plan",
            "write",
            "verify",
            "export",
            "report",
            "artifact",
            "markdown",
            "html",
            "ppt",
            "pptx",
            "|",
            "{",
            "}",
            "```",
        ]
        return any(marker in lower for marker in content_markers)

    @staticmethod
    def _should_emit_box(text: str, *, confirmed_hermes_box: bool = False) -> bool:
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

        if confirmed_hermes_box:
            return True

        return HermesCliWrapper._has_user_visible_signal(text)

    @staticmethod
    def _summarize_box_text(text: str, max_lines: int = 4) -> str | None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None
        if len(lines) <= max_lines:
            return "\n".join(lines)

        important_markers = [
            "\u62a5\u544a",
            "\u5df2\u751f\u6210",
            "\u5df2\u5b8c\u6210",
            "\u8f93\u51fa\u6587\u4ef6",
            "\u4fdd\u5b58\u5728",
            "ppt",
            "pptx",
            ".md",
            ".html",
            ".pptx",
            ".png",
            ".jpg",
            ".csv",
            ".xlsx",
        ]
        important_lines = [
            line
            for line in lines
            if any(marker.lower() in line.lower() for marker in important_markers)
        ]
        selected = important_lines[:max_lines] if important_lines else lines[:max_lines]
        return "\n".join(selected)

    async def ask_stream_events(
        self,
        question: str,
        session_id: str | None = None,
        run_id: str | None = None,
        conversation_id: str | None = None,
        working_dir: str | None = None,
        artifacts_dir: str | None = None,
    ) -> AsyncGenerator[HermesStreamEvent, None]:
        self.last_artifact_paths = []
        self.last_artifacts = []
        self.artifact_manifest_recorder = None
        self.artifact_watcher = None
        stream_started_at = datetime.now()
        self.stream_started_at = stream_started_at
        process_cwd: str | None = None
        managed_environment_keys = (
            "WEBAGENT_RUN_WORKSPACE",
            "HERMES_WORKSPACE",
            "WORKSPACE",
            "WEBAGENT_ARTIFACTS_DIR",
            "WEBAGENT_OUTPUT_DIR",
            "HERMES_ARTIFACTS_DIR",
            "WEBAGENT_CONVERSATION_ID",
            "WEBAGENT_RUN_ID",
            "WEBAGENT_RUNTIME_POLICY",
        )
        for key in managed_environment_keys:
            self._env.pop(key, None)

        if working_dir:
            shell_working_dir = self._shell_visible_path(working_dir)
            self._env.update(
                {
                    "WEBAGENT_RUN_WORKSPACE": shell_working_dir,
                    "HERMES_WORKSPACE": shell_working_dir,
                    "WORKSPACE": shell_working_dir,
                }
            )
            cwd_path = Path(working_dir).expanduser()
            if os.name != "nt" and cwd_path.exists():
                process_cwd = str(cwd_path)
        if artifacts_dir:
            shell_artifacts_dir = self._shell_visible_path(artifacts_dir)
            self._env.update(
                {
                    "WEBAGENT_ARTIFACTS_DIR": shell_artifacts_dir,
                    "WEBAGENT_OUTPUT_DIR": shell_artifacts_dir,
                    "HERMES_ARTIFACTS_DIR": shell_artifacts_dir,
                }
            )
        if conversation_id:
            self._env["WEBAGENT_CONVERSATION_ID"] = conversation_id
        if run_id:
            self._env["WEBAGENT_RUN_ID"] = run_id
        self._env["WEBAGENT_RUNTIME_POLICY"] = "managed-artifacts-v3"
        artifact_watcher: RunArtifactWatcher | None = None
        if run_id and artifacts_dir:
            self.artifact_manifest_recorder = ArtifactManifestRecorder(
                Path(artifacts_dir).expanduser() / ARTIFACT_MANIFEST_FILENAME,
                run_id=run_id,
                conversation_id=conversation_id,
                workspace_dir=working_dir,
                artifacts_dir=artifacts_dir,
            )
            artifact_watcher = RunArtifactWatcher(
                Path(working_dir or artifacts_dir).expanduser(),
                poll_interval_seconds=settings.artifact_watcher_poll_interval_seconds,
                stable_seconds=settings.artifact_watcher_stable_seconds,
                stable_samples=settings.artifact_watcher_stable_samples,
            )
            self.artifact_watcher = artifact_watcher
        self.last_diagnostics = {
            "artifact_paths": [],
            "artifacts": [],
            "exit_code": None,
            "last_stage": None,
            "raw_log_path": None,
            "stderr_tail": "",
            "stdout_tail": "",
            "working_dir": working_dir,
            "artifacts_dir": artifacts_dir,
            "conversation_id": conversation_id,
            "runtime_policy": "managed-artifacts-v3",
            "runtime_instruction_injected": False,
            "artifact_manifest_path": (
                str(self.artifact_manifest_recorder.path)
                if self.artifact_manifest_recorder is not None
                else None
            ),
            "artifact_manifest_schema": (
                ARTIFACT_MANIFEST_SCHEMA
                if self.artifact_manifest_recorder is not None
                else None
            ),
        }

        logger.info(
            "Starting Hermes stream: question_chars=%s session_id=%s",
            len(question),
            session_id or "",
        )
        session_message_cursors = self._session_message_counts()
        raw_log_path = self._raw_log_path(run_id)
        self.last_diagnostics["raw_log_path"] = str(raw_log_path)
        raw_log_path.write_text(
            (
                "Hermes raw stream log\n"
                f"started_at={datetime.now().isoformat()}\n"
                f"question_chars={len(question)} session_id={session_id or ''}\n\n"
            ),
            encoding="utf-8",
        )
        logger.info("Hermes raw output log: %s", raw_log_path)

        process = await asyncio.create_subprocess_exec(
            *self._build_chat_exec_args(
                question,
                session_id=session_id,
                quiet=False,
                use_pty=True,
                run_id=run_id,
            ),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=process_cwd,
        )
        if run_id:
            self.active_processes[run_id] = process
            register_run_process("hermes", run_id, process.pid)

        in_hermes_box = False
        box_lines: list[str] = []
        emitted_output = False
        emitted_artifact_count = 0
        last_emitted = ""
        stdout_tail = ""
        stderr_tail = ""
        final_output_tail = ""
        stderr_chunks: list[str] = []
        line_queue: asyncio.Queue[str | None] = asyncio.Queue()
        completion_detected = False
        completion_message_emitted = False
        last_raw_activity_emit = datetime.now()
        last_raw_summary = ""
        last_raw_summary_emit = datetime.min
        raw_activity_interval_seconds = 60
        should_stop_on_completion_signal = True
        last_artifact_poll_monotonic = 0.0
        last_session_poll_monotonic = 0.0
        last_session_activity_monotonic = asyncio.get_running_loop().time()
        session_artifact_candidates: set[str] = set()
        session_artifact_observations: dict[str, tuple[int, int, float, int]] = {}

        async def stop_after_completion() -> None:
            if process.returncode is not None:
                return
            logger.info(
                "Hermes completion signal received; stopping CLI after grace period."
            )
            await self._terminate_process_tree(process)

        async def flush_box() -> str | None:
            text = "\n".join(box_lines).strip()
            box_lines.clear()
            if not text or not self._should_emit_box(
                text,
                confirmed_hermes_box=True,
            ):
                return None
            return self._summarize_box_text(text)

        def heartbeat_event(
            content: str,
            *,
            heartbeat_type: str,
        ) -> HermesStreamEvent:
            self.last_diagnostics["last_stage"] = content
            self.last_diagnostics["stdout_tail"] = stdout_tail
            self.last_diagnostics["stderr_tail"] = stderr_tail
            return self._build_stream_event(
                content=content,
                raw_log_path=raw_log_path,
                run_id=run_id,
                completion_detected=False,
                artifact_found=False,
                payload={
                    "rawActivityHeartbeat": True,
                    "heartbeatType": heartbeat_type,
                    "stdoutTail": stdout_tail[-1000:],
                    "stderrTail": stderr_tail[-1000:],
                },
            )

        def artifact_transition_events(
            transitions: list[ArtifactFileTransition],
        ) -> list[HermesStreamEvent]:
            events: list[HermesStreamEvent] = []
            for transition in transitions:
                artifact_path = str(transition.path.resolve())
                self._remember_artifact_path(
                    artifact_path,
                    discovered_by="file_watcher",
                    status=transition.status,
                    size_bytes=transition.size_bytes,
                    mtime_ns=transition.mtime_ns,
                    stable_at=transition.stable_at,
                    error=transition.error,
                )
                artifact_item = next(
                    (
                        item
                        for item in self.last_artifacts
                        if item.get("artifact_path") == artifact_path
                    ),
                    {},
                )
                events.append(
                    self._build_stream_event(
                        content=f"Artifact {transition.path.name} is {transition.status}.",
                        raw_log_path=raw_log_path,
                        run_id=run_id,
                        completion_detected=False,
                        event_type_override="artifact_state",
                        payload={
                            "artifactState": transition.status,
                            "artifactPath": artifact_path,
                            "artifactType": self._artifact_type_from_path(artifact_path),
                            "artifactTitle": transition.path.stem,
                            "artifactRole": artifact_item.get("role"),
                            "manifestEntryId": artifact_item.get("entry_id"),
                            "manifestSchema": ARTIFACT_MANIFEST_SCHEMA,
                            "pathScope": artifact_item.get("path_scope"),
                            "sizeBytes": transition.size_bytes,
                            "mtimeNs": transition.mtime_ns,
                            "stableAt": (
                                transition.stable_at.isoformat()
                                if transition.stable_at
                                else None
                            ),
                            "error": transition.error,
                        },
                    )
                )
            return events

        def poll_artifact_watcher() -> list[ArtifactFileTransition]:
            nonlocal last_artifact_poll_monotonic
            if artifact_watcher is None:
                return []
            now_monotonic = asyncio.get_running_loop().time()
            if (
                now_monotonic - last_artifact_poll_monotonic
                < artifact_watcher.poll_interval_seconds
            ):
                return []
            last_artifact_poll_monotonic = now_monotonic
            return artifact_watcher.poll()

        def poll_session_recovery() -> tuple[list[str], list[str]]:
            nonlocal last_session_activity_monotonic, last_session_poll_monotonic

            now_monotonic = asyncio.get_running_loop().time()
            if now_monotonic - last_session_poll_monotonic < 1.0:
                return [], []
            last_session_poll_monotonic = now_monotonic
            assistant_updates, artifact_paths = self._recover_session_updates(
                started_at=stream_started_at,
                message_cursors=session_message_cursors,
            )
            if assistant_updates or artifact_paths:
                last_session_activity_monotonic = now_monotonic
            session_artifact_candidates.update(artifact_paths)

            stable_paths: list[str] = []
            for candidate in sorted(session_artifact_candidates):
                host_path = self._artifact_host_path(candidate)
                if not self._is_primary_completion_artifact(host_path):
                    continue
                try:
                    file_stat = host_path.stat()
                except OSError:
                    continue
                if file_stat.st_mtime < stream_started_at.timestamp() - 5:
                    continue
                previous = session_artifact_observations.get(candidate)
                signature = (file_stat.st_size, file_stat.st_mtime_ns)
                if previous is None or previous[:2] != signature:
                    session_artifact_observations[candidate] = (
                        file_stat.st_size,
                        file_stat.st_mtime_ns,
                        now_monotonic,
                        1,
                    )
                    continue
                unchanged_since = previous[2]
                unchanged_samples = previous[3] + 1
                session_artifact_observations[candidate] = (
                    file_stat.st_size,
                    file_stat.st_mtime_ns,
                    unchanged_since,
                    unchanged_samples,
                )
                if (
                    unchanged_samples < 2
                    or now_monotonic - unchanged_since < 1.5
                    or now_monotonic - last_session_activity_monotonic < 20
                ):
                    continue
                self._remember_artifact_path(
                    candidate,
                    discovered_by="recovery_scan",
                    status="ready",
                    size_bytes=file_stat.st_size,
                    mtime_ns=file_stat.st_mtime_ns,
                    stable_at=datetime.now(),
                )
                stable_paths.append(candidate)
            return assistant_updates, stable_paths

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
            nonlocal completion_detected, final_output_tail, stderr_tail, stdout_tail

            if stream is None:
                await line_queue.put(None)
                return

            stream_pending = ""
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

            async def consume_decoded(decoded: str) -> None:
                nonlocal completion_detected, final_output_tail
                nonlocal stderr_tail, stdout_tail, stream_pending
                if not decoded:
                    return
                with raw_log_path.open("a", encoding="utf-8", errors="replace") as raw_log:
                    raw_log.write(("STDERR " if is_stderr else "STDOUT ") + decoded)
                self._remember_artifact_paths(decoded)
                final_output_tail = (final_output_tail + decoded)[-131072:]
                if self._is_completion_signal(decoded):
                    completion_detected = True
                if is_stderr:
                    stderr_tail = (stderr_tail + decoded)[-4000:]
                    stderr_chunks.append(decoded)
                else:
                    stdout_tail = (stdout_tail + decoded)[-4000:]

                stream_pending += decoded.replace("\r", "\n")
                lines = stream_pending.split("\n")
                stream_pending = lines.pop() if lines else ""
                for raw_line in lines:
                    repaired_line = self._repair_mojibake_text(raw_line)
                    self._remember_artifact_paths(repaired_line)
                    if self._is_completion_signal(repaired_line):
                        completion_detected = True
                    await line_queue.put(repaired_line)

            while True:
                chunk = await stream.read(1024)
                if not chunk:
                    break

                await consume_decoded(decoder.decode(chunk))

            await consume_decoded(decoder.decode(b"", final=True))

            if stream_pending.strip():
                await line_queue.put(stream_pending)
            await line_queue.put(None)

        stream_tasks = [
            asyncio.create_task(read_stream(process.stdout, False)),
            asyncio.create_task(read_stream(process.stderr, True)),
        ]
        finished_streams = 0
        artifacts_before_final_discovery = 0

        try:
            while finished_streams < len(stream_tasks):
                try:
                    completion_timeout = (
                        8
                        if completion_detected and should_stop_on_completion_signal
                        else raw_activity_interval_seconds
                    )
                    if artifact_watcher is not None:
                        completion_timeout = min(
                            completion_timeout,
                            artifact_watcher.poll_interval_seconds,
                        )
                    raw_line = await asyncio.wait_for(
                        line_queue.get(),
                        timeout=completion_timeout,
                    )
                except TimeoutError:
                    if artifact_watcher is not None:
                        for artifact_event in artifact_transition_events(
                            poll_artifact_watcher()
                        ):
                            yield artifact_event
                    session_updates, stable_session_paths = poll_session_recovery()
                    for session_update in session_updates:
                        if not self._should_emit_box(session_update):
                            continue
                        summarized_update = self._summarize_box_text(session_update)
                        if not summarized_update or summarized_update == last_emitted:
                            continue
                        emitted_output = True
                        last_emitted = summarized_update
                        self.last_diagnostics["last_stage"] = summarized_update
                        yield self._build_stream_event(
                            content=summarized_update,
                            raw_log_path=raw_log_path,
                            run_id=run_id,
                            completion_detected=False,
                            artifact_found=False,
                            payload={"sessionTail": True},
                        )
                    if stable_session_paths:
                        completion_detected = True
                        completion_message_emitted = True
                        emitted_artifact_count = len(self.last_artifact_paths)
                        completed_names = ", ".join(
                            self._artifact_host_path(path).name
                            for path in stable_session_paths
                        )
                        completion_content = f"Hermes generated {completed_names}."
                        self.last_diagnostics["last_stage"] = completion_content
                        yield self._build_stream_event(
                            content=completion_content,
                            raw_log_path=raw_log_path,
                            run_id=run_id,
                            completion_detected=True,
                            artifact_found=True,
                            payload={"sessionArtifactCompletion": True},
                        )
                        await stop_after_completion()
                        break
                    if completion_detected and should_stop_on_completion_signal:
                        await stop_after_completion()
                        break
                    if process.returncode is not None:
                        break
                    now = datetime.now()
                    if (
                        now - last_raw_activity_emit
                    ).total_seconds() < raw_activity_interval_seconds:
                        continue
                    last_raw_activity_emit = now
                    yield heartbeat_event(
                        "Hermes 正在执行工具调用，等待下一段运行输出...",
                        heartbeat_type="process_alive",
                    )
                    continue

                if raw_line is None:
                    finished_streams += 1
                    continue

                if artifact_watcher is not None:
                    for artifact_event in artifact_transition_events(
                        poll_artifact_watcher()
                    ):
                        yield artifact_event

                if in_hermes_box and not raw_line.strip():
                    if box_lines and box_lines[-1] != "":
                        box_lines.append("")
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
                            completion_message_emitted = (
                                completion_message_emitted or completion_detected
                            )
                            artifact_found = len(self.last_artifact_paths) > emitted_artifact_count
                            emitted_artifact_count = len(self.last_artifact_paths)
                            logger.info("Hermes stage emitted: %s", flushed[:500])
                            yield self._build_stream_event(
                                content=flushed,
                                raw_log_path=raw_log_path,
                                run_id=run_id,
                                completion_detected=completion_detected,
                                artifact_found=artifact_found,
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
                        completion_message_emitted = (
                            completion_message_emitted or completion_detected
                        )
                        artifact_found = len(self.last_artifact_paths) > emitted_artifact_count
                        emitted_artifact_count = len(self.last_artifact_paths)
                        logger.info("Hermes stage emitted: %s", flushed[:500])
                        yield self._build_stream_event(
                            content=flushed,
                            raw_log_path=raw_log_path,
                            run_id=run_id,
                            completion_detected=completion_detected,
                            artifact_found=artifact_found,
                        )
                    in_hermes_box = False
                    continue

                if in_hermes_box and is_box_line:
                    continue

                if not in_hermes_box and text:
                    if self._is_completion_signal(text):
                        completion_detected = True
                        if should_stop_on_completion_signal:
                            await stop_after_completion()
                            break
                        continue

                    raw_summary = self._summarize_raw_runtime_line(text)
                    if raw_summary:
                        now = datetime.now()
                        should_emit_summary = (
                            raw_summary != last_raw_summary
                            or (now - last_raw_summary_emit).total_seconds() >= 18
                        )
                        if should_emit_summary:
                            last_raw_summary = raw_summary
                            last_raw_summary_emit = now
                            emitted_output = True
                            last_emitted = raw_summary
                            self.last_diagnostics["last_stage"] = raw_summary
                            artifact_found = len(self.last_artifact_paths) > emitted_artifact_count
                            emitted_artifact_count = len(self.last_artifact_paths)
                            yield self._build_stream_event(
                                content=raw_summary,
                                raw_log_path=raw_log_path,
                                run_id=run_id,
                                completion_detected=False,
                                artifact_found=artifact_found,
                                payload={"runtimeSummary": True, "rawLine": text[:500]},
                            )
                            continue

                    now = datetime.now()
                    if (
                        now - last_raw_activity_emit
                    ).total_seconds() >= raw_activity_interval_seconds:
                        last_raw_activity_emit = now
                        yield heartbeat_event(
                            "Hermes 正在持续输出运行日志，任务仍在执行...",
                            heartbeat_type="raw_output",
                        )
        except asyncio.CancelledError:
            if run_id:
                self.cancelled_run_ids.add(run_id)
            if self.artifact_manifest_recorder is not None:
                self.artifact_manifest_recorder.finalize(
                    failed=True,
                    error="Hermes run was cancelled before manifest finalization.",
                )
            await self._terminate_process_tree(process)
            raise

        if in_hermes_box:
            flushed = await flush_box()
            if flushed and flushed != last_emitted:
                emitted_output = True
                self.last_diagnostics["last_stage"] = flushed
                completion_detected = self._is_completion_signal(flushed)
                completion_message_emitted = (
                    completion_message_emitted or completion_detected
                )
                artifact_found = len(self.last_artifact_paths) > emitted_artifact_count
                emitted_artifact_count = len(self.last_artifact_paths)
                logger.info("Hermes stage emitted: %s", flushed[:500])
                yield self._build_stream_event(
                    content=flushed,
                    raw_log_path=raw_log_path,
                    run_id=run_id,
                    completion_detected=completion_detected,
                    artifact_found=artifact_found,
                )

        if completion_detected and should_stop_on_completion_signal:
            await stop_after_completion()

        try:
            await process.wait()
            await asyncio.gather(*stream_tasks)
            recovered_assistant_content = self._recover_latest_session_assistant_content(
                started_at=stream_started_at
            )
            if recovered_assistant_content:
                self._remember_artifact_paths(recovered_assistant_content)
                self._remember_final_output_artifact_paths(
                    recovered_assistant_content,
                    working_dir=working_dir,
                    artifacts_dir=artifacts_dir,
                )
            artifacts_before_final_discovery = emitted_artifact_count
            self._remember_final_output_artifact_paths(
                final_output_tail,
                working_dir=working_dir,
                artifacts_dir=artifacts_dir,
            )
            if artifact_watcher is not None:
                for artifact_event in artifact_transition_events(
                    await artifact_watcher.settle(
                        settings.artifact_watcher_settle_timeout_seconds
                    )
                ):
                    yield artifact_event
            self._discover_run_directory_artifacts(
                working_dir=working_dir,
                artifacts_dir=artifacts_dir,
                started_at=stream_started_at,
                failed_paths=(
                    artifact_watcher.failed_paths if artifact_watcher is not None else None
                ),
            )
            for artifact in self.last_artifacts:
                artifact["run_id"] = run_id
            manifest_snapshot: dict[str, object] | None = None
            if self.artifact_manifest_recorder is not None:
                manifest_failed = bool(
                    process.returncode != 0
                    and not completion_detected
                    and not self.last_artifact_paths
                )
                manifest_error = (
                    f"Hermes exited with code {process.returncode}." if manifest_failed else None
                )
                self.artifact_manifest_recorder.finalize(
                    failed=manifest_failed,
                    error=manifest_error,
                )
                manifest_snapshot = self.artifact_manifest_recorder.snapshot()
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
                    "artifact_manifest": manifest_snapshot,
                }
            )
            logger.info("Hermes stream process exited: returncode=%s", process.returncode)
        finally:
            if run_id and self.active_processes.get(run_id) is process:
                self.active_processes.pop(run_id, None)
            if run_id:
                await terminate_processes_by_marker(run_id)
                unregister_run_process(run_id, process.pid)

        if len(self.last_artifact_paths) > artifacts_before_final_discovery:
            discovered_count = len(self.last_artifact_paths) - artifacts_before_final_discovery
            yield self._build_stream_event(
                content=f"Hermes generated {discovered_count} artifact(s).",
                raw_log_path=raw_log_path,
                run_id=run_id,
                completion_detected=False,
                artifact_found=True,
                payload={"finalDiscovery": True},
            )

        if self.artifact_manifest_recorder is not None:
            yield self._build_stream_event(
                content=(
                    "Artifact manifest finalized with "
                    f"{len(self.artifact_manifest_recorder.manifest.artifacts)} artifact(s)."
                ),
                raw_log_path=raw_log_path,
                run_id=run_id,
                completion_detected=False,
                artifact_found=False,
                event_type_override="artifact_manifest_finalized",
                payload={
                    "artifactManifestFinalized": True,
                    "artifactManifestEntryCount": len(
                        self.artifact_manifest_recorder.manifest.artifacts
                    ),
                    "artifactManifestRecoveryUsed": (
                        self.artifact_manifest_recorder.manifest.recovery_used
                    ),
                },
            )
        if (
            recovered_assistant_content
            and not completion_message_emitted
            and recovered_assistant_content != last_emitted
        ):
            emitted_output = True
            completion_message_emitted = True
            last_emitted = recovered_assistant_content
            self.last_diagnostics["last_stage"] = recovered_assistant_content
            yield self._build_stream_event(
                content=recovered_assistant_content,
                raw_log_path=raw_log_path,
                run_id=run_id,
                completion_detected=True,
                artifact_found=bool(self.last_artifact_paths),
                payload={"sessionRecovery": True},
            )

        if (process.returncode == 0 or completion_detected) and not emitted_output:
            fallback_content = "Hermes completed. Discovering generated artifacts."
            self.last_diagnostics["last_stage"] = fallback_content
            yield self._build_stream_event(
                content=fallback_content,
                raw_log_path=raw_log_path,
                run_id=run_id,
                completion_detected=True,
                artifact_found=bool(self.last_artifact_paths),
                payload={"fallbackCompletion": True},
            )

        if run_id and run_id in self.cancelled_run_ids:
            self.cancelled_run_ids.discard(run_id)
            return

        if process.returncode != 0:
            stderr_str = "".join(stderr_chunks).strip()
            if completion_detected or self.last_artifact_paths:
                logger.warning(
                    "Hermes exited with code %s after completion/artifact signal; "
                    "treating as completed.",
                    process.returncode,
                )
                return

            diagnostic_tail = (stderr_tail or stdout_tail).strip()
            error_msg = (
                diagnostic_tail
                or stderr_str
                or f"Hermes exited with code {process.returncode}"
            )
            raise RuntimeError(f"Hermes CLI error: {error_msg}")
