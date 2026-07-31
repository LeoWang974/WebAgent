from os import name as os_name

from agent_runtime.adapters.hermes_cli import HermesCliWrapper


def test_hermes_wsl_command_sources_runtime_env():
    wrapper = HermesCliWrapper(hermes_home="/home/demo/.hermes", wsl_distribution="Ubuntu")

    command = wrapper._build_wsl_command(["/home/demo/.local/bin/hermes", "tools", "list"])

    assert "~/.hermes/.env" in command
    assert ".hermes/.env" in command
    assert "--noprofile --norc" in command
    assert "while IFS= read -r __line" in command
    assert "export \"$__line\"" in command
    assert "\"$__key\" != PATH" in command


def test_hermes_chat_exec_args_keep_prompt_out_of_shell():
    wrapper = HermesCliWrapper(hermes_home="/home/demo/.hermes", wsl_distribution="Ubuntu")

    args = wrapper._build_chat_exec_args(
        "Research global theme parks and analyze Disney's model.",
        skills="sn-research-report",
        toolsets="web,terminal,file",
        run_id="run_quote_test",
    )
    command = " ".join(args)

    assert "Disney's model" not in command
    assert "$(cat" not in command
    assert "python3 -c" in command
    assert "run_quote_test.txt" in command


def test_hermes_chat_exec_args_auto_approve_background_tool_calls():
    wrapper = HermesCliWrapper(hermes_home="/home/demo/.hermes", wsl_distribution="Ubuntu")

    args = wrapper._build_chat_exec_args(
        "Generate a report with the search tool.",
        skills="sn-deep-research",
        toolsets="web,terminal,file",
        run_id="run_yolo_test",
    )

    assert '"hermes", "--yolo", "chat", "-q"' in args[-1]


def test_hermes_chat_exec_args_avoid_windows_shell_quoting():
    wrapper = HermesCliWrapper(hermes_home="/home/demo/.hermes", wsl_distribution="Ubuntu")

    args = wrapper._build_chat_exec_args(
        "Research global theme parks and analyze Disney's model.",
        skills="sn-research-report",
        toolsets="web,terminal,file",
        run_id="run_exec_quote_test",
    )

    if os_name == "nt":
        assert args[:8] == [
            "wsl.exe",
            "-d",
            "Ubuntu",
            "--",
            "bash",
            "--noprofile",
            "--norc",
            "-c",
        ]
    else:
        assert args[:4] == ["bash", "--noprofile", "--norc", "-c"]
    assert "Disney's model" not in " ".join(args)
    assert "python3 -c" in args[-1]
    assert "run_exec_quote_test.txt" in args[-1]


def test_hermes_remembers_json_paths_as_debug_artifacts():
    wrapper = HermesCliWrapper()

    wrapper._remember_artifact_paths("/home/demo/.hermes/reports/topic/briefing.json")

    assert wrapper.last_artifact_paths == ["/home/demo/.hermes/reports/topic/briefing.json"]
    assert wrapper.last_artifacts[0]["artifact_type"] == "debug_json"
