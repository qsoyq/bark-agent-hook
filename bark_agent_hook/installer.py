from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from bark_agent_hook.constants import OPENCLAW_CONVERSATION_ACCESS_PATCH
from bark_agent_hook.models import AgentOption, CommandResult, InstallResult, InstallStatus

OPENCLAW_PLUGIN_ID = "bark-agent-hook-openclaw"
CLAUDE_CODE_ACP_PACKAGE = "@zed-industries/claude-code-acp"
CLAUDE_CODE_ACP_VERSION = "0.16.2"
CLAUDE_CODE_ACP_PACKAGE_SPEC = f"{CLAUDE_CODE_ACP_PACKAGE}@{CLAUDE_CODE_ACP_VERSION}"
CLAUDE_CODE_ACP_ADAPTER_NAME = "claude-code-acp-bark"
CLAUDE_CODE_ACP_MARKER = "bark-agent-hook claude-code-acp bridge"
CLAUDE_CODE_ACP_BRIDGE_CODE = """
function createBarkAgentHookBridge(logger = console) {
    return async (input) => {
        const { spawn } = await import("node:child_process");
        const child = spawn("bark-agent-hook", ["hook", "--runtime", "claude", "--event", "auto", "--summary-mode", "extract"], {
            stdio: ["pipe", "ignore", "pipe"],
        });
        let stderr = "";
        child.stderr?.on("data", (chunk) => {
            stderr += chunk.toString();
        });
        child.stdin.end(JSON.stringify(input ?? {}));
        const exitCode = await new Promise((resolve) => {
            child.on("error", (error) => {
                logger.error(`[bark-agent-hook] Claude Code ACP bridge failed to start: ${error instanceof Error ? error.message : String(error)}`);
                resolve(0);
            });
            child.on("close", resolve);
        });
        if (exitCode !== 0 && stderr.trim()) {
            logger.error(`[bark-agent-hook] Claude Code ACP bridge exited ${exitCode}: ${stderr.trim()}`);
        }
        return { continue: true };
    };
}
""".strip()


def _run_install_command(args: list[str], *, input_text: str | None = None) -> CommandResult:
    proc = subprocess.run(
        args,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(args=args, returncode=proc.returncode, stdout=proc.stdout or "", stderr=proc.stderr or "")


def _run_required(args: list[str], *, input_text: str | None = None) -> CommandResult:
    result = _run_install_command(args, input_text=input_text)
    if result.returncode != 0:
        raise RuntimeError(_command_failure_message(result))
    return result


def _run_required_idempotent(args: list[str], *, input_text: str | None = None) -> CommandResult:
    result = _run_install_command(args, input_text=input_text)
    if result.returncode == 0 or _looks_already_configured(result):
        return result
    raise RuntimeError(_command_failure_message(result))


def _run_required_cwd(args: list[str], cwd: Path, *, input_text: str | None = None) -> CommandResult:
    env = os.environ.copy()
    env["npm_config_cache"] = str(cwd / ".npm-cache")
    proc = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    result = CommandResult(args=args, returncode=proc.returncode, stdout=proc.stdout or "", stderr=proc.stderr or "")
    if result.returncode != 0:
        raise RuntimeError(_command_failure_message(result))
    return result


def _looks_already_configured(result: CommandResult) -> bool:
    message = f"{result.stdout} {result.stderr}".lower()
    return "already" in message and any(word in message for word in ("exist", "configured", "installed", "enabled"))


def _command_failure_message(result: CommandResult) -> str:
    detail = " ".join((result.stderr or result.stdout).split())
    command = " ".join(result.args)
    if detail:
        return f"{command} exited {result.returncode}: {detail}"
    return f"{command} exited {result.returncode}"


def _json_from_command(args: list[str]) -> Any:
    result = _run_install_command(args)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _codex_installed_version() -> str | None:
    data = _json_from_command(["codex", "plugin", "list", "--json"])
    if not isinstance(data, dict):
        return None
    installed = data.get("installed")
    if not isinstance(installed, list):
        return None
    for item in installed:
        if not isinstance(item, dict):
            continue
        if item.get("pluginId") == "bark-agent-hook-codex@bark-agent-hook":
            version = item.get("version")
            return str(version) if version is not None else None
    return None


def _claude_installed_version() -> str | None:
    data = _json_from_command(["claude", "plugin", "list", "--json"])
    if not isinstance(data, list):
        return None
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("id") == "bark-agent-hook@bark-agent-hook" and item.get("scope") == "user":
            version = item.get("version")
            return str(version) if version is not None else None
    return None


def _find_version(value: Any) -> str | None:
    if isinstance(value, dict):
        version = value.get("version")
        if version is not None and not isinstance(version, dict | list):
            return str(version)
        for item in value.values():
            found = _find_version(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_version(item)
            if found:
                return found
    return None


def _openclaw_installed_version() -> str | None:
    data = _json_from_command(["openclaw", "plugins", "inspect", OPENCLAW_PLUGIN_ID, "--runtime", "--json"])
    if isinstance(data, dict):
        plugin = data.get("plugin")
        if isinstance(plugin, dict):
            version = plugin.get("version")
            if version is not None and not isinstance(version, dict | list):
                return str(version)
    return _find_version(data)


def _parse_version_parts(version: str) -> list[int] | None:
    parts: list[int] = []
    for raw_part in version.split("."):
        if not raw_part.isdigit():
            return None
        parts.append(int(raw_part))
    return parts or None


def _version_change(before: str | None, after: str | None) -> InstallStatus:
    if before is None:
        return "installed"
    if after is None:
        return "updated"
    if before == after:
        return "unchanged"
    before_parts = _parse_version_parts(before)
    after_parts = _parse_version_parts(after)
    if before_parts is None or after_parts is None:
        return "updated"
    return "updated" if after_parts > before_parts else "downgraded"


def _uninstall_version_change(before: str | None, after: str | None) -> InstallStatus:
    if before is None:
        return "unchanged"
    if after is None:
        return "removed"
    return "unchanged"


def _bark_agent_home() -> Path:
    raw_home = os.environ.get("BARK_AGENT_HOOK_HOME")
    if raw_home and raw_home.strip():
        return Path(raw_home).expanduser()
    return Path.home() / ".bark-agent-hook"


def _claude_code_acp_adapter_dir() -> Path:
    return _bark_agent_home() / CLAUDE_CODE_ACP_ADAPTER_NAME


def _claude_code_acp_bin_dir() -> Path:
    return _bark_agent_home() / "bin"


def _claude_code_acp_launcher_path() -> Path:
    return _claude_code_acp_bin_dir() / CLAUDE_CODE_ACP_ADAPTER_NAME


def _claude_code_acp_entrypoint(adapter_dir: Path) -> Path:
    return adapter_dir / "node_modules" / "@zed-industries" / "claude-code-acp" / "dist" / "index.js"


def _claude_code_acp_agent_file(adapter_dir: Path) -> Path:
    return adapter_dir / "node_modules" / "@zed-industries" / "claude-code-acp" / "dist" / "acp-agent.js"


def _openclaw_plugin_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "plugins" / "bark-agent-hook-openclaw"


def _read_openclaw_plugin_id(plugin_dir: Path) -> str | None:
    manifest_path = plugin_dir / "openclaw.plugin.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    plugin_id = data.get("id")
    return str(plugin_id) if plugin_id is not None and not isinstance(plugin_id, dict | list) else None


def _same_openclaw_plugin_path(left: Path, right: Path) -> bool:
    return left.expanduser().resolve() == right.expanduser().resolve()


def _dedupe_openclaw_plugin_load_paths(plugin_dir: Path) -> None:
    data = _json_from_command(["openclaw", "config", "get", "plugins.load.paths", "--json"])
    if not isinstance(data, list):
        return

    configured_paths = [item for item in data if isinstance(item, str) and item.strip()]
    plugin_dir_text = str(plugin_dir)
    kept_paths: list[str] = []
    current_path_seen = False
    changed = len(configured_paths) != len(data)

    for configured_path in configured_paths:
        path = Path(configured_path)
        if _same_openclaw_plugin_path(path, plugin_dir):
            if current_path_seen:
                changed = True
                continue
            current_path_seen = True
            if configured_path != plugin_dir_text:
                changed = True
            kept_paths.append(plugin_dir_text)
            continue

        if _read_openclaw_plugin_id(path) == OPENCLAW_PLUGIN_ID:
            changed = True
            continue
        kept_paths.append(configured_path)

    if not current_path_seen:
        kept_paths.append(plugin_dir_text)
        changed = True
    if not changed:
        return

    _run_required(["openclaw", "config", "patch", "--stdin"], input_text=json.dumps({"plugins": {"load": {"paths": kept_paths}}}))


def _install_codex(cli_path: str) -> InstallResult:
    before = _codex_installed_version()
    try:
        _run_required_idempotent(["codex", "plugin", "marketplace", "add", "qsoyq/bark-agent-hook"])
        _run_required(["codex", "plugin", "marketplace", "upgrade", "bark-agent-hook"])
        _run_required_idempotent(["codex", "plugin", "add", "bark-agent-hook-codex@bark-agent-hook"])
    except RuntimeError as e:
        return InstallResult("Codex", "failed", before, None, cli_path, str(e), _extract_command_from_error(str(e)))
    after = _codex_installed_version()
    status = _version_change(before, after)
    return InstallResult("Codex", status, before, after, cli_path, cli_path)


def _install_claude(cli_path: str) -> InstallResult:
    before = _claude_installed_version()
    try:
        _run_required_idempotent(["claude", "plugin", "marketplace", "add", "qsoyq/bark-agent-hook", "--scope", "user"])
        _run_required(["claude", "plugin", "marketplace", "update", "bark-agent-hook"])
        if before is None:
            _run_required(["claude", "plugin", "install", "bark-agent-hook@bark-agent-hook", "--scope", "user"])
        else:
            _run_required(["claude", "plugin", "update", "bark-agent-hook@bark-agent-hook", "--scope", "user"])
    except RuntimeError as e:
        return InstallResult("Claude Code", "failed", before, None, cli_path, str(e), _extract_command_from_error(str(e)))
    after = _claude_installed_version()
    status = _version_change(before, after)
    return InstallResult("Claude Code", status, before, after, cli_path, cli_path)


def _install_openclaw(cli_path: str) -> InstallResult:
    before = _openclaw_installed_version()
    plugin_dir = _openclaw_plugin_dir()
    if not plugin_dir.is_dir():
        return InstallResult(
            "OpenClaw",
            "failed",
            before,
            None,
            cli_path,
            f"Missing local plugin directory: {plugin_dir}",
        )
    try:
        _run_required_idempotent(["openclaw", "plugins", "install", "--link", str(plugin_dir)])
        _dedupe_openclaw_plugin_load_paths(plugin_dir)
        _run_required_idempotent(["openclaw", "plugins", "enable", OPENCLAW_PLUGIN_ID])
        _run_required(["openclaw", "config", "patch", "--stdin"], input_text=OPENCLAW_CONVERSATION_ACCESS_PATCH)
        _run_required(["openclaw", "plugins", "registry", "--refresh", "--json"])
        _run_required(["openclaw", "gateway", "restart"])
    except RuntimeError as e:
        return InstallResult("OpenClaw", "failed", before, None, cli_path, str(e), _extract_command_from_error(str(e)))
    after = _openclaw_installed_version()
    status = _version_change(before, after)
    return InstallResult("OpenClaw", status, before, after, cli_path, cli_path)


def _claude_code_acp_installed_version() -> str | None:
    package_json = _claude_code_acp_adapter_dir() / "node_modules" / "@zed-industries" / "claude-code-acp" / "package.json"
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return str(version) if version is not None and not isinstance(version, dict | list) else None


def _write_claude_code_acp_package_json(adapter_dir: Path) -> None:
    package_json = {
        "private": True,
        "type": "module",
        "dependencies": {
            CLAUDE_CODE_ACP_PACKAGE: CLAUDE_CODE_ACP_VERSION,
        },
    }
    (adapter_dir / "package.json").write_text(json.dumps(package_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _patch_claude_code_acp_agent(agent_file: Path) -> None:
    source = agent_file.read_text(encoding="utf-8")
    if CLAUDE_CODE_ACP_MARKER in source:
        return
    bridge_function = f"\n// {CLAUDE_CODE_ACP_MARKER}\n{CLAUDE_CODE_ACP_BRIDGE_CODE}\n"
    source = source.replace("const ALLOW_BYPASS = !IS_ROOT || !!process.env.IS_SANDBOX;\n", f"const ALLOW_BYPASS = !IS_ROOT || !!process.env.IS_SANDBOX;\n{bridge_function}\n", 1)

    pre_hook = "{\n                        hooks: [createPreToolUseHook(settingsManager, this.logger)],\n                    },"
    patched_pre_hook = "{\n                        hooks: [createBarkAgentHookBridge(this.logger), createPreToolUseHook(settingsManager, this.logger)],\n                    },"
    source = source.replace(pre_hook, patched_pre_hook, 1)

    post_hook = "hooks: [\n                            createPostToolUseHook(this.logger,"
    patched_post_hook = "hooks: [\n                            createBarkAgentHookBridge(this.logger),\n                            createPostToolUseHook(this.logger,"
    source = source.replace(post_hook, patched_post_hook, 1)

    hook_anchor = "hooks: {\n                ...userProvidedOptions?.hooks,\n"
    extra_hooks = """hooks: {
                ...userProvidedOptions?.hooks,
                Notification: [
                    ...(userProvidedOptions?.hooks?.Notification || []),
                    {
                        hooks: [createBarkAgentHookBridge(this.logger)],
                    },
                ],
                PermissionRequest: [
                    ...(userProvidedOptions?.hooks?.PermissionRequest || []),
                    {
                        hooks: [createBarkAgentHookBridge(this.logger)],
                    },
                ],
                Stop: [
                    ...(userProvidedOptions?.hooks?.Stop || []),
                    {
                        hooks: [createBarkAgentHookBridge(this.logger)],
                    },
                ],
                SessionEnd: [
                    ...(userProvidedOptions?.hooks?.SessionEnd || []),
                    {
                        hooks: [createBarkAgentHookBridge(this.logger)],
                    },
                ],
"""
    source = source.replace(hook_anchor, extra_hooks, 1)

    if CLAUDE_CODE_ACP_MARKER not in source or patched_pre_hook not in source or patched_post_hook not in source or "Notification: [" not in source or "Stop: [" not in source:
        raise RuntimeError(f"Unable to patch {agent_file}; {CLAUDE_CODE_ACP_PACKAGE_SPEC} layout may have changed")
    agent_file.write_text(source, encoding="utf-8")


def _write_claude_code_acp_launcher(launcher_path: Path, node_path: str, entrypoint: Path) -> None:
    launcher = f"""#!/bin/sh
exec {json.dumps(node_path)} {json.dumps(str(entrypoint))} "$@"
"""
    launcher_path.parent.mkdir(parents=True, exist_ok=True)
    launcher_path.write_text(launcher, encoding="utf-8")
    launcher_path.chmod(0o755)


def _install_zed_claude_code_acp(node_path: str) -> InstallResult:
    before = _claude_code_acp_installed_version()
    adapter_dir = _claude_code_acp_adapter_dir()
    launcher_path = _claude_code_acp_launcher_path()
    if shutil.which("npm") is None:
        return InstallResult("Zed Claude Code ACP", "failed", before, None, node_path, "npm CLI not found")
    try:
        adapter_dir.mkdir(parents=True, exist_ok=True)
        _write_claude_code_acp_package_json(adapter_dir)
        _run_required_cwd(["npm", "install", "--omit=dev", "--ignore-scripts"], adapter_dir)
        agent_file = _claude_code_acp_agent_file(adapter_dir)
        entrypoint = _claude_code_acp_entrypoint(adapter_dir)
        if not agent_file.is_file() or not entrypoint.is_file():
            raise RuntimeError(f"{CLAUDE_CODE_ACP_PACKAGE_SPEC} did not install the expected ACP entry files")
        _patch_claude_code_acp_agent(agent_file)
        _write_claude_code_acp_launcher(launcher_path, node_path, entrypoint)
    except RuntimeError as e:
        return InstallResult("Zed Claude Code ACP", "failed", before, None, node_path, str(e), _extract_command_from_error(str(e)))
    except OSError as e:
        return InstallResult("Zed Claude Code ACP", "failed", before, None, node_path, str(e))
    after = _claude_code_acp_installed_version()
    status = _version_change(before, after)
    return InstallResult("Zed Claude Code ACP", status, before, after, node_path, f"Launcher: {launcher_path}")


def _uninstall_codex(cli_path: str) -> InstallResult:
    before = _codex_installed_version()
    if before is None:
        return InstallResult("Codex", "unchanged", before, None, cli_path, "Plugin not installed")
    try:
        _run_required_idempotent(["codex", "plugin", "remove", "bark-agent-hook-codex@bark-agent-hook"])
    except RuntimeError as e:
        return InstallResult("Codex", "failed", before, None, cli_path, str(e), _extract_command_from_error(str(e)))
    after = _codex_installed_version()
    status = _uninstall_version_change(before, after)
    note = cli_path if status == "removed" else "Plugin still appears installed"
    return InstallResult("Codex", status, before, after, cli_path, note)


def _uninstall_claude(cli_path: str) -> InstallResult:
    before = _claude_installed_version()
    if before is None:
        return InstallResult("Claude Code", "unchanged", before, None, cli_path, "Plugin not installed")
    try:
        _run_required_idempotent(["claude", "plugin", "uninstall", "bark-agent-hook@bark-agent-hook", "--scope", "user"])
    except RuntimeError as e:
        return InstallResult("Claude Code", "failed", before, None, cli_path, str(e), _extract_command_from_error(str(e)))
    after = _claude_installed_version()
    status = _uninstall_version_change(before, after)
    note = cli_path if status == "removed" else "Plugin still appears installed"
    return InstallResult("Claude Code", status, before, after, cli_path, note)


def _openclaw_supports_plugins_command(command: str) -> bool:
    return _run_install_command(["openclaw", "plugins", command, "--help"]).returncode == 0


def _uninstall_openclaw(cli_path: str) -> InstallResult:
    before = _openclaw_installed_version()
    if before is None:
        return InstallResult("OpenClaw", "unchanged", before, None, cli_path, "Plugin not installed")
    remove_command: list[str] | None = None
    try:
        _run_required_idempotent(["openclaw", "plugins", "disable", "bark-agent-hook-openclaw"])
        if _openclaw_supports_plugins_command("remove"):
            remove_command = ["openclaw", "plugins", "remove", "bark-agent-hook-openclaw"]
        elif _openclaw_supports_plugins_command("uninstall"):
            remove_command = ["openclaw", "plugins", "uninstall", "bark-agent-hook-openclaw"]
        if remove_command is not None:
            _run_required_idempotent(remove_command)
        _run_required(["openclaw", "gateway", "restart"])
    except RuntimeError as e:
        return InstallResult("OpenClaw", "failed", before, None, cli_path, str(e), _extract_command_from_error(str(e)))
    after = _openclaw_installed_version()
    status = _uninstall_version_change(before, after)
    note = cli_path if status == "removed" else "Plugin disabled; remove command unavailable or inspect still reports it"
    return InstallResult("OpenClaw", status, before, after, cli_path, note)


def _uninstall_zed_claude_code_acp(_node_path: str) -> InstallResult:
    before = _claude_code_acp_installed_version()
    adapter_dir = _claude_code_acp_adapter_dir()
    launcher_path = _claude_code_acp_launcher_path()
    removed = False
    try:
        if launcher_path.exists():
            launcher_path.unlink()
            removed = True
        if adapter_dir.exists():
            shutil.rmtree(adapter_dir)
            removed = True
    except OSError as e:
        return InstallResult("Zed Claude Code ACP", "failed", before, before, str(launcher_path), str(e))
    status: InstallStatus = "removed" if before is not None or removed else "unchanged"
    note = "Removed local Claude Code ACP Bark adapter" if status == "removed" else "Local Claude Code ACP Bark adapter not installed"
    return InstallResult("Zed Claude Code ACP", status, before, None, str(launcher_path), note)


def _extract_command_from_error(message: str) -> list[str] | None:
    command = message.split(" exited ", 1)[0].strip()
    return command.split() if command else None


def _selected_agent_values(agents: list[AgentOption] | None) -> set[str] | None:
    if not agents:
        return None
    return {agent.value for agent in agents}


def _run_for_available_agents(agents: list[AgentOption] | None, actions: list[tuple[str, str, Any]]) -> list[InstallResult]:
    selected = _selected_agent_values(agents)
    results: list[InstallResult] = []
    for agent, command, action in actions:
        if selected is not None and command not in selected:
            continue
        cli_command = "node" if command == "zed-claude-code-acp" else command
        cli_path = shutil.which(cli_command)
        if cli_path is None:
            results.append(InstallResult(agent, "skipped", None, None, None, f"{cli_command} CLI not found"))
            continue
        results.append(action(cli_path))
    return results


def _include_explicit_action(agents: list[AgentOption] | None, action_value: str) -> bool:
    selected = _selected_agent_values(agents)
    return selected is not None and action_value in selected


def _install_for_available_agents(agents: list[AgentOption] | None = None) -> list[InstallResult]:
    actions: list[tuple[str, str, Any]] = [
        ("Codex", "codex", _install_codex),
        ("Claude Code", "claude", _install_claude),
        ("OpenClaw", "openclaw", _install_openclaw),
    ]
    if _include_explicit_action(agents, "zed-claude-code-acp"):
        actions.append(("Zed Claude Code ACP", "zed-claude-code-acp", _install_zed_claude_code_acp))
    return _run_for_available_agents(
        agents,
        actions,
    )


def _uninstall_for_available_agents(agents: list[AgentOption] | None = None) -> list[InstallResult]:
    actions: list[tuple[str, str, Any]] = [
        ("Codex", "codex", _uninstall_codex),
        ("Claude Code", "claude", _uninstall_claude),
        ("OpenClaw", "openclaw", _uninstall_openclaw),
    ]
    if _include_explicit_action(agents, "zed-claude-code-acp"):
        actions.append(("Zed Claude Code ACP", "zed-claude-code-acp", _uninstall_zed_claude_code_acp))
    return _run_for_available_agents(
        agents,
        actions,
    )
