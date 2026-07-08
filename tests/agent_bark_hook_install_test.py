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
    assert all("zed-claude-code-acp" not in args for args in calls)


def test_install_default_does_not_install_zed_claude_code_acp(monkeypatch):
    calls = []

    def fake_which(command):
        return {
            "codex": "/opt/homebrew/bin/codex",
            "claude": "/Users/me/.local/bin/claude",
            "openclaw": "/usr/local/bin/openclaw",
            "node": "/opt/homebrew/bin/node",
            "npm": "/opt/homebrew/bin/npm",
        }.get(command)

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["codex", "plugin", "list", "--json"]:
            return _Completed(args, stdout=json.dumps({"installed": []}))
        if args == ["claude", "plugin", "list", "--json"]:
            return _Completed(args, stdout=json.dumps([]))
        if args == ["openclaw", "plugins", "inspect", "bark-agent-hook-openclaw", "--runtime", "--json"]:
            return _Completed(args, stdout=json.dumps({}))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["install"])

    assert result.exit_code == 0
    assert "Zed Claude Code ACP" not in result.output
    assert "bark-agent-hook install --agent zed-claude-code-acp" in result.output
    assert "claude-code-acp-bark" in result.output
    assert ["npm", "install", "--omit=dev", "--ignore-scripts"] not in calls


def test_install_zed_claude_code_acp_creates_local_launcher(monkeypatch, tmp_path):
    calls = []
    home = tmp_path / "home"
    adapter_dir = home / "claude-code-acp-bark"
    package_dir = adapter_dir / "node_modules" / "@zed-industries" / "claude-code-acp"
    dist_dir = package_dir / "dist"

    upstream_agent = """const ALLOW_BYPASS = !IS_ROOT || !!process.env.IS_SANDBOX;
const options = {
            hooks: {
                ...userProvidedOptions?.hooks,
                PreToolUse: [
                    ...(userProvidedOptions?.hooks?.PreToolUse || []),
                    {
                        hooks: [createPreToolUseHook(settingsManager, this.logger)],
                    },
                ],
                PostToolUse: [
                    ...(userProvidedOptions?.hooks?.PostToolUse || []),
                    {
                        hooks: [
                            createPostToolUseHook(this.logger, {
                                onEnterPlanMode: async () => {},
                            }),
                        ],
                    },
                ],
            },
};
"""

    def fake_which(command):
        return {
            "node": "/opt/homebrew/bin/node",
            "npm": "/opt/homebrew/bin/npm",
        }.get(command)

    def fake_run(args, **kwargs):
        calls.append((args, kwargs.get("cwd")))
        if args == ["npm", "install", "--omit=dev", "--ignore-scripts"]:
            dist_dir.mkdir(parents=True)
            (package_dir / "package.json").write_text(json.dumps({"version": "0.16.2"}), encoding="utf-8")
            (dist_dir / "index.js").write_text("import './acp-agent.js';\n", encoding="utf-8")
            (dist_dir / "acp-agent.js").write_text(upstream_agent, encoding="utf-8")
        return _Completed(args)

    monkeypatch.setenv("BARK_AGENT_HOOK_HOME", str(home))
    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["install", "--agent", "zed-claude-code-acp"])

    assert result.exit_code == 0
    assert "Zed Claude Code ACP" in result.output
    assert "installed" in result.output
    assert "npx -y @zed-industries/claude-code-acp" in result.output
    assert (home / "bin" / "claude-code-acp-bark").is_file()
    patched_agent = (dist_dir / "acp-agent.js").read_text(encoding="utf-8")
    assert "bark-agent-hook claude-code-acp bridge" in patched_agent
    assert "const { spawn } = await import" in patched_agent
    assert "{{ spawn }}" not in patched_agent
    assert "createBarkAgentHookBridge(this.logger), createPreToolUseHook" in patched_agent
    assert any(args == ["npm", "install", "--omit=dev", "--ignore-scripts"] and cwd == adapter_dir for args, cwd in calls)


def test_install_zed_claude_code_acp_creates_windows_cmd_launcher(monkeypatch, tmp_path):
    calls = []
    home = tmp_path / "home"
    adapter_dir = home / "claude-code-acp-bark"
    package_dir = adapter_dir / "node_modules" / "@zed-industries" / "claude-code-acp"
    dist_dir = package_dir / "dist"

    upstream_agent = """const ALLOW_BYPASS = !IS_ROOT || !!process.env.IS_SANDBOX;
const options = {
            hooks: {
                ...userProvidedOptions?.hooks,
                PreToolUse: [
                    ...(userProvidedOptions?.hooks?.PreToolUse || []),
                    {
                        hooks: [createPreToolUseHook(settingsManager, this.logger)],
                    },
                ],
                PostToolUse: [
                    ...(userProvidedOptions?.hooks?.PostToolUse || []),
                    {
                        hooks: [
                            createPostToolUseHook(this.logger, {
                                onEnterPlanMode: async () => {},
                            }),
                        ],
                    },
                ],
            },
};
"""

    def fake_which(command):
        return {
            "node": r"C:\Program Files\nodejs\node.exe",
            "npm": r"C:\Program Files\nodejs\npm.cmd",
        }.get(command)

    def fake_run(args, **kwargs):
        calls.append((args, kwargs.get("cwd")))
        if args == ["npm", "install", "--omit=dev", "--ignore-scripts"]:
            dist_dir.mkdir(parents=True)
            (package_dir / "package.json").write_text(json.dumps({"version": "0.16.2"}), encoding="utf-8")
            (dist_dir / "index.js").write_text("import './acp-agent.js';\n", encoding="utf-8")
            (dist_dir / "acp-agent.js").write_text(upstream_agent, encoding="utf-8")
        return _Completed(args)

    monkeypatch.setenv("BARK_AGENT_HOOK_HOME", str(home))
    monkeypatch.setattr(agent_bark_installer, "_is_windows", lambda: True)
    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_hook.cmd, ["install", "--agent", "zed-claude-code-acp"])

    launcher = home / "bin" / "claude-code-acp-bark.cmd"
    assert result.exit_code == 0
    assert "Zed Claude Code ACP" in result.output
    assert "cmd" in result.output
    assert launcher.is_file()
    assert not (home / "bin" / "claude-code-acp-bark").exists()
    launcher_text = launcher.read_text(encoding="utf-8")
    assert launcher_text.startswith("@echo off\n")
    assert '"C:\\\\Program Files\\\\nodejs\\\\node.exe"' in launcher_text
    assert json.dumps(str(dist_dir / "index.js")) in launcher_text
    assert "%*" in launcher_text
    assert any(args == ["npm", "install", "--omit=dev", "--ignore-scripts"] and cwd == adapter_dir for args, cwd in calls)


def test_install_zed_claude_code_acp_requires_npm(monkeypatch, tmp_path):
    home = tmp_path / "home"

    def fake_which(command):
        return "/opt/homebrew/bin/node" if command == "node" else None

    monkeypatch.setenv("BARK_AGENT_HOOK_HOME", str(home))
    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)

    result = runner.invoke(agent_bark_hook.cmd, ["install", "--agent", "zed-claude-code-acp"])

    assert result.exit_code == 1
    assert "Zed Claude Code ACP" in result.output
    assert "failed" in result.output
    assert "npm CLI not found" in result.output


def test_uninstall_zed_claude_code_acp_removes_local_adapter(monkeypatch, tmp_path):
    home = tmp_path / "home"
    adapter_dir = home / "claude-code-acp-bark"
    package_dir = adapter_dir / "node_modules" / "@zed-industries" / "claude-code-acp"
    launcher = home / "bin" / "claude-code-acp-bark"
    package_dir.mkdir(parents=True)
    launcher.parent.mkdir(parents=True)
    (package_dir / "package.json").write_text(json.dumps({"version": "0.16.2"}), encoding="utf-8")
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setenv("BARK_AGENT_HOOK_HOME", str(home))
    monkeypatch.setattr(agent_bark_hook.shutil, "which", lambda command: "/opt/homebrew/bin/node" if command == "node" else None)

    result = runner.invoke(agent_bark_hook.cmd, ["uninstall", "--agent", "zed-claude-code-acp"])

    assert result.exit_code == 0
    assert "Zed Claude Code ACP" in result.output
    assert "removed" in result.output
    assert not adapter_dir.exists()
    assert not launcher.exists()


def test_uninstall_zed_claude_code_acp_removes_windows_and_legacy_launchers(monkeypatch, tmp_path):
    home = tmp_path / "home"
    adapter_dir = home / "claude-code-acp-bark"
    package_dir = adapter_dir / "node_modules" / "@zed-industries" / "claude-code-acp"
    cmd_launcher = home / "bin" / "claude-code-acp-bark.cmd"
    legacy_launcher = home / "bin" / "claude-code-acp-bark"
    package_dir.mkdir(parents=True)
    cmd_launcher.parent.mkdir(parents=True)
    (package_dir / "package.json").write_text(json.dumps({"version": "0.16.2"}), encoding="utf-8")
    cmd_launcher.write_text("@echo off\n", encoding="utf-8")
    legacy_launcher.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setenv("BARK_AGENT_HOOK_HOME", str(home))
    monkeypatch.setattr(agent_bark_installer, "_is_windows", lambda: True)
    monkeypatch.setattr(agent_bark_hook.shutil, "which", lambda command: r"C:\\Program Files\\nodejs\\node.exe" if command == "node" else None)

    result = runner.invoke(agent_bark_hook.cmd, ["uninstall", "--agent", "zed-claude-code-acp"])

    assert result.exit_code == 0
    assert "Zed Claude Code ACP" in result.output
    assert "removed" in result.output
    assert not adapter_dir.exists()
    assert not cmd_launcher.exists()
    assert not legacy_launcher.exists()


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


def test_openclaw_installed_version_prefers_runtime_plugin_version(monkeypatch):
    def fake_run(args, **kwargs):
        if args == ["openclaw", "plugins", "inspect", "bark-agent-hook-openclaw", "--runtime", "--json"]:
            return _Completed(args, stdout=json.dumps({"install": {"version": "0.1.5"}, "plugin": {"version": "0.1.1"}}))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    assert agent_bark_installer._openclaw_installed_version() == "0.1.1"


def test_install_openclaw_dedupes_stale_plugin_load_paths_and_refreshes_registry(monkeypatch, tmp_path):
    calls = []
    openclaw_versions = iter(["0.1.1", "0.1.5"])
    current_plugin_dir = tmp_path / "current" / "bark-agent-hook-openclaw"
    old_plugin_dir = tmp_path / "old" / "bark-agent-hook-openclaw"
    other_plugin_dir = tmp_path / "other"
    unknown_dir = tmp_path / "unknown"
    for path in (current_plugin_dir, old_plugin_dir, other_plugin_dir, unknown_dir):
        path.mkdir(parents=True)
    (current_plugin_dir / "openclaw.plugin.json").write_text(json.dumps({"id": "bark-agent-hook-openclaw", "version": "0.1.5"}))
    (old_plugin_dir / "openclaw.plugin.json").write_text(json.dumps({"id": "bark-agent-hook-openclaw", "version": "0.1.1"}))
    (other_plugin_dir / "openclaw.plugin.json").write_text(json.dumps({"id": "other-plugin", "version": "2.0.0"}))

    def fake_which(command):
        return "/usr/local/bin/openclaw" if command == "openclaw" else None

    def fake_run(args, **kwargs):
        calls.append((args, kwargs.get("input")))
        if args == ["openclaw", "plugins", "inspect", "bark-agent-hook-openclaw", "--runtime", "--json"]:
            version = next(openclaw_versions)
            return _Completed(args, stdout=json.dumps({"plugin": {"version": version}, "install": {"version": "0.1.5"}}))
        if args == ["openclaw", "config", "get", "plugins.load.paths", "--json"]:
            return _Completed(
                args,
                stdout=json.dumps(
                    [
                        str(old_plugin_dir),
                        str(current_plugin_dir),
                        str(current_plugin_dir),
                        str(other_plugin_dir),
                        str(unknown_dir),
                    ]
                ),
            )
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)
    monkeypatch.setattr(agent_bark_installer, "_openclaw_plugin_dir", lambda: current_plugin_dir)

    result = runner.invoke(agent_bark_hook.cmd, ["install", "--agent", "openclaw"])

    assert result.exit_code == 0
    assert "updated" in result.output
    assert "0.1.1 -> 0.1.5" in result.output
    patch_payloads = [json.loads(input_text) for args, input_text in calls if args == ["openclaw", "config", "patch", "--stdin"] and input_text]
    load_path_patches = [payload for payload in patch_payloads if "load" in payload.get("plugins", {})]
    assert load_path_patches == [
        {
            "plugins": {
                "load": {
                    "paths": [
                        str(current_plugin_dir),
                        str(other_plugin_dir),
                        str(unknown_dir),
                    ]
                }
            }
        }
    ]
    called_args = [args for args, _ in calls]
    assert ["openclaw", "plugins", "install", "--link", str(current_plugin_dir)] in called_args
    assert ["openclaw", "plugins", "registry", "--refresh", "--json"] in called_args
    assert called_args.index(["openclaw", "plugins", "registry", "--refresh", "--json"]) < called_args.index(["openclaw", "gateway", "restart"])


def test_install_openclaw_keeps_idempotent_single_current_plugin_path(monkeypatch, tmp_path):
    calls = []
    openclaw_versions = iter(["0.1.5", "0.1.5"])
    current_plugin_dir = tmp_path / "current" / "bark-agent-hook-openclaw"
    current_plugin_dir.mkdir(parents=True)
    (current_plugin_dir / "openclaw.plugin.json").write_text(json.dumps({"id": "bark-agent-hook-openclaw", "version": "0.1.5"}))

    def fake_which(command):
        return "/usr/local/bin/openclaw" if command == "openclaw" else None

    def fake_run(args, **kwargs):
        calls.append((args, kwargs.get("input")))
        if args == ["openclaw", "plugins", "inspect", "bark-agent-hook-openclaw", "--runtime", "--json"]:
            version = next(openclaw_versions)
            return _Completed(args, stdout=json.dumps({"plugin": {"version": version}}))
        if args == ["openclaw", "config", "get", "plugins.load.paths", "--json"]:
            return _Completed(args, stdout=json.dumps([str(current_plugin_dir)]))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_hook.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)
    monkeypatch.setattr(agent_bark_installer, "_openclaw_plugin_dir", lambda: current_plugin_dir)

    result = runner.invoke(agent_bark_hook.cmd, ["install", "--agent", "openclaw"])

    assert result.exit_code == 0
    assert "unchanged" in result.output
    patch_payloads = [json.loads(input_text) for args, input_text in calls if args == ["openclaw", "config", "patch", "--stdin"] and input_text]
    assert {"plugins": {"load": {"paths": [str(current_plugin_dir)]}}} not in patch_payloads
    assert ["openclaw", "plugins", "registry", "--refresh", "--json"] in [args for args, _ in calls]


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
        "多个",
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
