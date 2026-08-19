# File purpose: Verifies test hermes env behavior and its regression contracts.
# Main declarations: test_hermes_marks_serper_as_configured_from_runtime_settings verifies hermes
# marks serper as configured from runtime settings;
# test_hermes_repairs_gb18030_mojibake_from_pty_output verifies hermes repairs gb18030 mojibake
# from pty output; test_hermes_keeps_valid_chinese_unchanged verifies hermes keeps valid chinese
# unchanged; test_hermes_emits_concise_chinese_box_reply_without_punctuation verifies hermes emits
# concise chinese box reply without punctuation;
# test_hermes_chat_exec_args_keep_prompt_out_of_shell verifies hermes chat exec args keep prompt
# out of shell; test_hermes_chat_exec_args_auto_approve_background_tool_calls verifies hermes chat
# exec args auto approve background tool calls;
# test_hermes_chat_exec_args_avoid_windows_shell_quoting verifies hermes chat exec args avoid
# windows shell quoting; test_hermes_remembers_json_paths_as_debug_artifacts verifies hermes
# remembers json paths as debug artifacts.

from os import name as os_name

from app.integrations.hermes import HermesCliWrapper


def test_hermes_marks_serper_as_configured_from_runtime_settings():
    wrapper = HermesCliWrapper(serper_configured=True)

    assert wrapper._env["WEBAGENT_SERPER_CONFIGURED"] == "1"


def test_hermes_repairs_gb18030_mojibake_from_pty_output():
    expected = "编码正常"
    mojibake = expected.encode("utf-8").decode("gb18030")

    assert HermesCliWrapper._repair_mojibake_text(mojibake) == expected


def test_hermes_keeps_valid_chinese_unchanged():
    text = "最终验收通过"

    assert HermesCliWrapper._repair_mojibake_text(text) == text


def test_hermes_emits_concise_chinese_box_reply_without_punctuation():
    assert HermesCliWrapper._should_emit_box("最终中文回复正常") is True


def test_hermes_chat_exec_args_keep_prompt_out_of_shell():
    wrapper = HermesCliWrapper(hermes_home="/home/demo/.hermes", wsl_distribution="Ubuntu")

    args = wrapper._build_chat_exec_args(
        "Research global theme parks and analyze Disney's model.",
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
        run_id="run_yolo_test",
    )

    assert '"hermes", "--yolo", "chat", "-q"' in args[-1]


def test_hermes_chat_exec_args_avoid_windows_shell_quoting():
    wrapper = HermesCliWrapper(hermes_home="/home/demo/.hermes", wsl_distribution="Ubuntu")

    args = wrapper._build_chat_exec_args(
        "Research global theme parks and analyze Disney's model.",
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
