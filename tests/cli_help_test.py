from typer.testing import CliRunner

from bark_agent_hook import hook as agent_bark_hook

runner = CliRunner()


def _plain(text: str) -> str:
    return text.replace("\x1b", "")


def test_root_help_contains_install_guidance_without_plugins_group():
    result = runner.invoke(agent_bark_hook.cmd, ["--help"])
    output = _plain(result.output)

    assert result.exit_code == 0
    assert "bark-agent-hook install" in output
    assert "agent" in output
    assert "codex" in output
    assert "bark-agent-hook uninstall" in output
    assert "codex plugin marketplace add qsoyq/bark-agent-hook" in output
    assert "claude plugin install bark-agent-hook@bark-agent-hook" in output
    assert "openclaw plugins install" in output
    assert "./plugins/bark-agent-hook-openclaw" in output
    assert "BARK_DEVICE_KEY" in output
    assert "AGENT_BARK_NOTIFY_HOOK_URL" in output
    assert "plugins list" not in output
    assert "config-snippet" not in output
    assert "install-guide" not in output
