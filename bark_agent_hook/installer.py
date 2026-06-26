from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from bark_agent_hook.constants import OPENCLAW_CONVERSATION_ACCESS_PATCH
from bark_agent_hook.models import AgentOption, CommandResult, InstallResult, InstallStatus

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
    data = _json_from_command(["openclaw", "plugins", "inspect", "bark-agent-hook-openclaw", "--runtime", "--json"])
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


def _openclaw_plugin_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "plugins" / "bark-agent-hook-openclaw"


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
        _run_required_idempotent(["openclaw", "plugins", "enable", "bark-agent-hook-openclaw"])
        _run_required(["openclaw", "config", "patch", "--stdin"], input_text=OPENCLAW_CONVERSATION_ACCESS_PATCH)
        _run_required(["openclaw", "gateway", "restart"])
    except RuntimeError as e:
        return InstallResult("OpenClaw", "failed", before, None, cli_path, str(e), _extract_command_from_error(str(e)))
    after = _openclaw_installed_version()
    status = _version_change(before, after)
    return InstallResult("OpenClaw", status, before, after, cli_path, cli_path)


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
        cli_path = shutil.which(command)
        if cli_path is None:
            results.append(InstallResult(agent, "skipped", None, None, None, "CLI not found"))
            continue
        results.append(action(cli_path))
    return results


def _install_for_available_agents(agents: list[AgentOption] | None = None) -> list[InstallResult]:
    return _run_for_available_agents(
        agents,
        [
            ("Codex", "codex", _install_codex),
            ("Claude Code", "claude", _install_claude),
            ("OpenClaw", "openclaw", _install_openclaw),
        ],
    )


def _uninstall_for_available_agents(agents: list[AgentOption] | None = None) -> list[InstallResult]:
    return _run_for_available_agents(
        agents,
        [
            ("Codex", "codex", _uninstall_codex),
            ("Claude Code", "claude", _uninstall_claude),
            ("OpenClaw", "openclaw", _uninstall_openclaw),
        ],
    )
