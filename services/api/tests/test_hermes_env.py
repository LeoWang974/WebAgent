from agent_runtime.adapters.hermes_cli import HermesCliWrapper


def test_hermes_wsl_command_sources_runtime_env():
    wrapper = HermesCliWrapper(hermes_home="/home/demo/.hermes", wsl_distribution="Ubuntu")

    command = wrapper._build_wsl_command(["/home/demo/.local/bin/hermes", "tools", "list"])

    assert "/home/demo/.hermes/.env" in command
    assert "while IFS= read -r __line" in command
    assert "export \"$__line\"" in command
    assert "\"$__key\" != PATH" in command
