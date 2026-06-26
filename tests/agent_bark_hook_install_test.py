import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from bark_agent_hook import hook as agent_bark_hook
from bark_agent_hook import installer as agent_bark_installer

runner = CliRunner()

OLD_AGENT_BARK_NOTIFY_PREFIX = "AI_ASSISTANT" + "_AGENT_BARK_NOTIFY_"
OPENCLAW_PLUGIN_WHEEL_FILES = {
    "plugins/bark-agent-hook-openclaw/package.json",
    "plugins/bark-agent-hook-openclaw/openclaw.plugin.json",
    "plugins/bark-agent-hook-openclaw/README.md",
    "plugins/bark-agent-hook-openclaw/index.js",
}
REPO_ROOT = Path(__file__).resolve().parents[1]


class _Completed:
    def __init__(self, args, returncode=0, stdout="", stderr=""):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _plain(text: str) -> str:
    return " ".join(text.replace("│", " ").replace("┃", " ").replace("┏", " ").replace("┓", " ").replace("└", " ").replace("┘", " ").split())


def test_wheel_includes_openclaw_plugin_assets_and_resolves_installed_plugin_dir(tmp_path):
    dist_dir = tmp_path / "dist"
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist_dir)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr

    wheels = sorted(dist_dir.glob("bark_agent_hook-*.whl"))
    assert len(wheels) == 1

    with zipfile.ZipFile(wheels[0]) as wheel:
        wheel_files = set(wheel.namelist())
        wheel.extractall(tmp_path / "site-packages")

    assert OPENCLAW_PLUGIN_WHEEL_FILES <= wheel_files

    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path / "site-packages")
    installed_result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from bark_agent_hook.hook import _openclaw_plugin_dir; "
            "plugin_dir = _openclaw_plugin_dir(); "
            "assert plugin_dir.is_dir(), plugin_dir; "
            "expected = {'package.json', 'openclaw.plugin.json', 'README.md', 'index.js'}; "
            "assert expected <= {path.name for path in plugin_dir.iterdir()}, plugin_dir",
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert installed_result.returncode == 0, installed_result.stdout + installed_result.stderr


def test_install_skips_missing_agent_clis(monkeypatch):
    monkeypatch.setattr(agent_bark_hook.shutil, "which", lambda command: None)

    result = runner.invoke(agent_bark_hook.cmd, ["install"])

    assert result.exit_code == 0
    assert "Codex" in result.output
    assert "Claude Code" in result.output
    assert "OpenClaw" in result.output
    assert "skipped" in result.output
    assert "CLI not found" in result.output
    assert "Summary: 0 succeeded, 3 skipped, 0 failed." in result.output
    assert "BARK_DEVICE_KEY=<your Bark device key>" in result.output
    assert OLD_AGENT_BARK_NOTIFY_PREFIX not in result.output


def test_install_agent_option_limits_selected_agents(monkeypatch):
    calls = []
    codex_versions = iter([None, "0.1.0"])

    def fake_which(command):
        return {
            "codex": "/opt/homebrew/bin/codex",
            "claude": "/Users/me/.local/bin/claude",
            "openclaw": "/usr/local/bin/openclaw",
        }.get(command)

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["codex", "plugin", "list", "--json"]:
            version = next(codex_versions)
            installed = [] if version is None else [{"pluginId": "bark-agent-hook-codex@bark-agent-hook", "version": version}]
            return _Completed(args, stdout=json.dumps({"installed": installed}))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["install", "--agent", "codex"])

    assert result.exit_code == 0
    assert "Codex" in result.output
    assert "Claude Code" not in result.output
    assert "OpenClaw" not in result.output
    assert ["codex", "plugin", "add", "bark-agent-hook-codex@bark-agent-hook"] in calls
    assert ["claude", "plugin", "list", "--json"] not in calls
    assert ["openclaw", "plugins", "inspect", "bark-agent-hook-openclaw", "--runtime", "--json"] not in calls


def test_install_repeated_agent_option_runs_selected_agents(monkeypatch):
    calls = []
    codex_versions = iter([None, "0.1.0"])
    claude_versions = iter([None, "0.1.0"])

    def fake_which(command):
        return {
            "codex": "/opt/homebrew/bin/codex",
            "claude": "/Users/me/.local/bin/claude",
            "openclaw": "/usr/local/bin/openclaw",
        }.get(command)

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["codex", "plugin", "list", "--json"]:
            version = next(codex_versions)
            installed = [] if version is None else [{"pluginId": "bark-agent-hook-codex@bark-agent-hook", "version": version}]
            return _Completed(args, stdout=json.dumps({"installed": installed}))
        if args == ["claude", "plugin", "list", "--json"]:
            version = next(claude_versions)
            return _Completed(args, stdout=json.dumps([] if version is None else [{"id": "bark-agent-hook@bark-agent-hook", "scope": "user", "version": version}]))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["install", "--agent", "codex", "--agent", "claude"])

    assert result.exit_code == 0
    assert "Codex" in result.output
    assert "Claude Code" in result.output
    assert "OpenClaw" not in result.output
    assert ["codex", "plugin", "add", "bark-agent-hook-codex@bark-agent-hook"] in calls
    assert ["claude", "plugin", "install", "bark-agent-hook@bark-agent-hook", "--scope", "user"] in calls
    assert ["openclaw", "plugins", "inspect", "bark-agent-hook-openclaw", "--runtime", "--json"] not in calls


def test_install_codex_first_install(monkeypatch):
    calls = []
    codex_versions = iter([None, "0.1.0"])

    def fake_which(command):
        return "/opt/homebrew/bin/codex" if command == "codex" else None

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["codex", "plugin", "list", "--json"]:
            version = next(codex_versions)
            installed = [] if version is None else [{"pluginId": "bark-agent-hook-codex@bark-agent-hook", "version": version}]
            return _Completed(args, stdout=json.dumps({"installed": installed}))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["install"])

    assert result.exit_code == 0
    assert "Codex" in result.output
    assert "installed" in result.output
    assert "none -> 0.1.0" in result.output
    assert ["codex", "plugin", "marketplace", "add", "qsoyq/bark-agent-hook"] in calls
    assert ["codex", "plugin", "marketplace", "upgrade", "bark-agent-hook"] in calls
    assert ["codex", "plugin", "add", "bark-agent-hook-codex@bark-agent-hook"] in calls


def test_install_codex_continues_when_marketplace_is_already_configured(monkeypatch):
    codex_versions = iter([None, "0.1.0"])

    def fake_which(command):
        return "/opt/homebrew/bin/codex" if command == "codex" else None

    def fake_run(args, **kwargs):
        if args == ["codex", "plugin", "list", "--json"]:
            version = next(codex_versions)
            installed = [] if version is None else [{"pluginId": "bark-agent-hook-codex@bark-agent-hook", "version": version}]
            return _Completed(args, stdout=json.dumps({"installed": installed}))
        if args == ["codex", "plugin", "marketplace", "add", "qsoyq/bark-agent-hook"]:
            return _Completed(args, returncode=1, stderr="marketplace already configured")
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["install"])

    assert result.exit_code == 0
    assert "installed" in result.output
    assert "none -> 0.1.0" in result.output


def test_install_claude_updates_existing_user_plugin(monkeypatch):
    calls = []
    claude_versions = iter(["0.0.9", "0.1.0"])

    def fake_which(command):
        return "/Users/me/.local/bin/claude" if command == "claude" else None

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["claude", "plugin", "list", "--json"]:
            version = next(claude_versions)
            return _Completed(args, stdout=json.dumps([{"id": "bark-agent-hook@bark-agent-hook", "scope": "user", "version": version}]))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["install"])

    assert result.exit_code == 0
    assert "Claude Code" in result.output
    assert "updated" in result.output
    assert "0.0.9 -> 0.1.0" in result.output
    assert ["claude", "plugin", "marketplace", "add", "qsoyq/bark-agent-hook", "--scope", "user"] in calls
    assert ["claude", "plugin", "marketplace", "update", "bark-agent-hook"] in calls
    assert ["claude", "plugin", "update", "bark-agent-hook@bark-agent-hook", "--scope", "user"] in calls
    assert ["claude", "plugin", "install", "bark-agent-hook@bark-agent-hook", "--scope", "user"] not in calls


def test_install_reports_downgrade(monkeypatch):
    codex_versions = iter(["0.1.0", "0.0.9"])

    def fake_which(command):
        return "/opt/homebrew/bin/codex" if command == "codex" else None

    def fake_run(args, **kwargs):
        if args == ["codex", "plugin", "list", "--json"]:
            version = next(codex_versions)
            return _Completed(args, stdout=json.dumps({"installed": [{"pluginId": "bark-agent-hook-codex@bark-agent-hook", "version": version}]}))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["install"])

    assert result.exit_code == 0
    assert "downgraded" in result.output
    assert "0.1.0 -> 0.0.9" in result.output


def test_install_reports_unchanged(monkeypatch):
    codex_versions = iter(["0.1.0", "0.1.0"])

    def fake_which(command):
        return "/opt/homebrew/bin/codex" if command == "codex" else None

    def fake_run(args, **kwargs):
        if args == ["codex", "plugin", "list", "--json"]:
            version = next(codex_versions)
            return _Completed(args, stdout=json.dumps({"installed": [{"pluginId": "bark-agent-hook-codex@bark-agent-hook", "version": version}]}))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["install"])

    assert result.exit_code == 0
    assert "unchanged" in result.output
    assert "0.1.0" in result.output


def test_install_continues_after_agent_failure(monkeypatch):
    codex_versions = iter([None, "0.1.0"])
    claude_versions = iter(["0.0.9"])

    def fake_which(command):
        return {
            "codex": "/opt/homebrew/bin/codex",
            "claude": "/Users/me/.local/bin/claude",
        }.get(command)

    def fake_run(args, **kwargs):
        if args == ["codex", "plugin", "list", "--json"]:
            version = next(codex_versions)
            installed = [] if version is None else [{"pluginId": "bark-agent-hook-codex@bark-agent-hook", "version": version}]
            return _Completed(args, stdout=json.dumps({"installed": installed}))
        if args == ["claude", "plugin", "list", "--json"]:
            version = next(claude_versions)
            return _Completed(args, stdout=json.dumps([{"id": "bark-agent-hook@bark-agent-hook", "scope": "user", "version": version}]))
        if args == ["claude", "plugin", "update", "bark-agent-hook@bark-agent-hook", "--scope", "user"]:
            return _Completed(args, returncode=1, stderr="update failed")
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["install"])

    assert result.exit_code == 0
    assert "Codex" in result.output
    assert "installed" in result.output
    assert "Claude Code" in result.output
    assert "failed" in result.output
    assert "Summary: 1 succeeded, 1 skipped, 1 failed." in result.output
    assert "claude plugin update bark-agent-hook@bark-agent-hook --scope user" in result.output


def test_install_exits_one_when_all_found_agents_fail(monkeypatch):
    def fake_which(command):
        return "/opt/homebrew/bin/codex" if command == "codex" else None

    def fake_run(args, **kwargs):
        if args == ["codex", "plugin", "list", "--json"]:
            return _Completed(args, stdout=json.dumps({"installed": []}))
        if args == ["codex", "plugin", "marketplace", "add", "qsoyq/bark-agent-hook"]:
            return _Completed(args, returncode=1, stderr="network failed")
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["install"])

    assert result.exit_code == 1
    assert "Codex" in result.output
    assert "failed" in result.output
    assert "Summary: 0 succeeded, 2 skipped, 1 failed." in result.output


def test_install_openclaw_fails_when_local_plugin_directory_is_missing(monkeypatch, tmp_path):
    def fake_which(command):
        return "/usr/local/bin/openclaw" if command == "openclaw" else None

    def fake_run(args, **kwargs):
        if args == ["openclaw", "plugins", "inspect", "bark-agent-hook-openclaw", "--runtime", "--json"]:
            return _Completed(args, stdout=json.dumps({"version": "0.1.0"}))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)
    monkeypatch.setattr(agent_bark_installer, "_openclaw_plugin_dir", lambda: tmp_path / "missing")

    result = runner.invoke(agent_bark_hook.cmd, ["install"])

    assert result.exit_code == 1
    assert "OpenClaw" in result.output
    assert "failed" in result.output
    assert "Missing local plugin directory" in result.output
    assert "source checkout" in result.output


def test_install_handles_invalid_json_versions(monkeypatch):
    def fake_which(command):
        return "/opt/homebrew/bin/codex" if command == "codex" else None

    def fake_run(args, **kwargs):
        if args == ["codex", "plugin", "list", "--json"]:
            return _Completed(args, stdout="{not json")
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["install"])

    assert result.exit_code == 0
    assert "installed" in result.output
    assert "none -> unknown" in result.output


def test_install_help_describes_scope_plugins_and_environment():
    result = runner.invoke(agent_bark_hook.cmd, ["install", "--help"])
    output = _plain(result.output)

    assert result.exit_code == 0
    for expected in (
        "codex",
        "claude",
        "openclaw",
        "agent",
        "multiple agents",
        "bark-agent-hook-codex@bark-agent-hook",
        "bark-agent-hook@bark-agent-hook",
    ):
        assert expected in output
    assert OLD_AGENT_BARK_NOTIFY_PREFIX not in output


def test_uninstall_codex_removes_installed_plugin(monkeypatch):
    calls = []
    codex_versions = iter(["0.1.0", None])

    def fake_which(command):
        return "/opt/homebrew/bin/codex" if command == "codex" else None

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["codex", "plugin", "list", "--json"]:
            version = next(codex_versions)
            installed = [] if version is None else [{"pluginId": "bark-agent-hook-codex@bark-agent-hook", "version": version}]
            return _Completed(args, stdout=json.dumps({"installed": installed}))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["uninstall", "--agent", "codex"])

    assert result.exit_code == 0
    assert "removed" in result.output
    assert "0.1.0 -> unknown" in result.output
    assert ["codex", "plugin", "remove", "bark-agent-hook-codex@bark-agent-hook"] in calls
    assert "Marketplace sources, environment variables, and historical audit logs were left unchanged." in _plain(result.output)


def test_uninstall_agent_option_limits_selected_agents(monkeypatch):
    calls = []
    claude_versions = iter(["0.1.0", None])

    def fake_which(command):
        return {
            "codex": "/opt/homebrew/bin/codex",
            "claude": "/Users/me/.local/bin/claude",
            "openclaw": "/usr/local/bin/openclaw",
        }.get(command)

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["claude", "plugin", "list", "--json"]:
            version = next(claude_versions)
            return _Completed(args, stdout=json.dumps([] if version is None else [{"id": "bark-agent-hook@bark-agent-hook", "scope": "user", "version": version}]))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["uninstall", "--agent", "claude"])

    assert result.exit_code == 0
    assert "Claude Code" in result.output
    assert "Codex" not in result.output
    assert "OpenClaw" not in result.output
    assert ["claude", "plugin", "uninstall", "bark-agent-hook@bark-agent-hook", "--scope", "user"] in calls
    assert ["codex", "plugin", "list", "--json"] not in calls
    assert ["openclaw", "plugins", "inspect", "bark-agent-hook-openclaw", "--runtime", "--json"] not in calls


def test_uninstall_openclaw_disables_removes_and_restarts_gateway(monkeypatch):
    calls = []
    openclaw_versions = iter(["0.1.0", None])

    def fake_which(command):
        return "/usr/local/bin/openclaw" if command == "openclaw" else None

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["openclaw", "plugins", "inspect", "bark-agent-hook-openclaw", "--runtime", "--json"]:
            version = next(openclaw_versions)
            return _Completed(args, stdout=json.dumps({} if version is None else {"version": version}))
        if args == ["openclaw", "plugins", "remove", "--help"]:
            return _Completed(args)
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["uninstall", "--agent", "openclaw"])

    assert result.exit_code == 0
    assert "removed" in result.output
    assert ["openclaw", "plugins", "disable", "bark-agent-hook-openclaw"] in calls
    assert ["openclaw", "plugins", "remove", "bark-agent-hook-openclaw"] in calls
    assert ["openclaw", "gateway", "restart"] in calls
