import re

from typer.testing import CliRunner

from bark_agent_hook import hook as agent_bark_hook

runner = CliRunner()
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _plain(text: str) -> str:
    return ANSI_RE.sub("", text)


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
    assert "从 agent 生命周期 hook 和直接 CLI 请求发送 Bark 通知" in output
    assert "AGENT_BARK_NOTIFY_AUDIT_LOG_FILE 在启用审计日志时默认" in output
    assert "~/.bark-agent-hook/bark-agent-hook.log" in output
    assert "{repo_or_project}, {workdir}, {branch}, {workspace}, {runtime}" in output
    assert "{repo_or_project}: 在 git 仓库内为仓库顶层目录名" in output
    assert "示例: BARK_GROUP='{repo_or_project}@{branch}'" in output
    assert "plugins list" not in output
    assert "config-snippet" not in output
    assert "install-guide" not in output


def test_hook_help_lists_template_variables_with_chinese_descriptions():
    result = runner.invoke(agent_bark_hook.cmd, ["hook", "--help"])
    output = _plain(result.output)

    assert result.exit_code == 0
    assert "从 stdin 读取 hook JSON，并尽力发送 Bark 通知" in output
    assert "配置:" in output
    assert "模板变量:" in output
    assert "AGENT_BARK_NOTIFY_TITLE_TEMPLATE 支持" in output
    assert "{agent}, {event}, {project}, {branch}, {session}, {runtime}" in output
    assert "{cwd_basename}" in output
    assert "{model}, {provider}" in output
    assert "BARK_GROUP 支持" in output
    for value in ("{repo_or_project}", "{workdir}", "{branch}", "{workspace}", "{runtime}", "{model}", "{provider}"):
        assert value in output
    assert "{repo_or_project}: 在 git 仓库内为仓库顶层目录名" in output
    assert "{workspace}: Lody workspace 会话" in output
    assert "AGENT_BARK_NOTIFY_HOOK_URL 支持" in output
    assert "{session_key}, {conversation_id}, {message_id}, {run_id}, {agent_id}" in output
    assert "{workspace_dir}, {cwd_basename}, {model}, {provider}" in output
    assert "Hook URL 变量值会做 percent-encode" in output


def test_send_help_lists_direct_bark_options_with_descriptions():
    result = runner.invoke(agent_bark_hook.cmd, ["send", "--help"])
    output = _plain(result.output)

    assert result.exit_code == 0
    assert "直接发送一条 Bark 通知" in output
    assert "--server" in output
    assert "Bark 服务端基础" in output
    assert "BARK_SERVER" in output
    assert "--device-key" in output
    assert "Bark device" in output
    assert "--markdown" in output
    assert "Markdown" in output
    assert "推送正文" in output
    assert "--auto-copy" in output
    assert "自动复制推送内容" in output
    assert "--archive" in output
    assert "保存到 Bark" in output
    assert "历史" in output
    assert "--param" in output
    assert "额外 Bark 参数" in output
