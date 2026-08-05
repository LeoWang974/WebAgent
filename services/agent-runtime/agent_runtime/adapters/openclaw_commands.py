import os
import shlex

from ..schemas import AgentRunCreate


def build_openclaw_message(input_data: AgentRunCreate) -> str:
    return input_data.content


def with_runtime_env(command: str, extra_env: dict[str, str | None] | None = None) -> str:
    extra_exports = ""
    cwd_command = ""
    path_prefix = (extra_env or {}).get("WEBAGENT_AGENT_PATH_PREFIX") or os.environ.get(
        "WEBAGENT_AGENT_PATH_PREFIX"
    )
    if path_prefix:
        extra_exports += f"export PATH={shlex.quote(path_prefix)}:$PATH; "
    for key, value in (extra_env or {}).items():
        if value and key != "WEBAGENT_AGENT_PATH_PREFIX":
            extra_exports += f"export {key}={shlex.quote(value)}; "
    agent_cwd = (extra_env or {}).get("WEBAGENT_AGENT_CWD")
    if agent_cwd:
        quoted_cwd = shlex.quote(agent_cwd)
        cwd_command = f"mkdir -p {quoted_cwd}; cd {quoted_cwd}; "
    return (
        "unset OPENCLAW_BASE_URL OPENCLAW_GATEWAY_URL; "
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
        "unset OPENCLAW_BASE_URL OPENCLAW_GATEWAY_URL; "
        f"{extra_exports}"
        f"{cwd_command}"
        f"{command}"
    )


def build_cli_args(
    args: list[str],
    *,
    cli_path: str,
    runtime_env: dict[str, str | None],
) -> list[str]:
    if os.name == "nt" and cli_path != "openclaw":
        return [cli_path, *args]

    executable = "openclaw" if os.name == "nt" else cli_path
    command = " ".join(shlex.quote(str(arg)) for arg in [executable, *args])
    command = with_runtime_env(command, runtime_env)
    if os.name == "nt" and cli_path == "openclaw":
        return ["wsl.exe", "--", "bash", "-lc", command]
    return ["bash", "-lc", command]


def build_shell_args(command: str, runtime_env: dict[str, str | None]) -> list[str]:
    command = with_runtime_env(command, runtime_env)
    if os.name == "nt":
        return ["wsl.exe", "--", "bash", "-lc", command]
    return ["bash", "-lc", command]


def build_agent_cli_args(
    input_data: AgentRunCreate,
    *,
    agent_id: str,
    cli_path: str,
    command_timeout_seconds: int,
    mode: str,
    runtime_env: dict[str, str | None],
) -> list[str]:
    args = [
        "agent",
        "--agent",
        agent_id,
        "--message",
        build_openclaw_message(input_data),
        "--json",
        "--timeout",
        str(max(1, command_timeout_seconds)),
    ]
    if mode == "local_cli":
        args.insert(1, "--local")
    if input_data.session_id:
        args.extend(["--session-id", input_data.session_id])
    return build_cli_args(args, cli_path=cli_path, runtime_env=runtime_env)
