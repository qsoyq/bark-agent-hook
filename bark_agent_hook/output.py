from __future__ import annotations

from rich.console import Console
from rich.table import Table

from bark_agent_hook.models import InstallResult, InstallStatus


def _version_text(before: str | None, after: str | None) -> str:
    before_text = before or "none"
    after_text = after or "unknown"
    if before is not None and after is not None and before == after:
        return after
    return f"{before_text} -> {after_text}"


def _status_style(status: InstallStatus) -> str:
    return {
        "installed": "green",
        "updated": "cyan",
        "downgraded": "yellow",
        "unchanged": "blue",
        "removed": "green",
        "failed": "red",
        "skipped": "dim",
    }[status]


def _succeeded(results: list[InstallResult]) -> int:
    return sum(1 for result in results if result.status in {"installed", "updated", "downgraded", "unchanged", "removed"})


def _skipped(results: list[InstallResult]) -> int:
    return sum(1 for result in results if result.status == "skipped")


def _failed(results: list[InstallResult]) -> int:
    return sum(1 for result in results if result.status == "failed")


def _found_cli_count(results: list[InstallResult]) -> int:
    return sum(1 for result in results if result.status != "skipped")


def _print_action_results(results: list[InstallResult], console: Console, *, title: str) -> None:
    console.print(f"[bold]{title}[/bold]")
    console.print()
    table = Table()
    table.add_column("Agent")
    table.add_column("Status")
    table.add_column("Version")
    table.add_column("CLI / Notes")
    for result in results:
        note = result.note
        if result.status in {"installed", "updated", "downgraded", "unchanged", "removed"} and result.cli_path and result.note == result.cli_path:
            note = result.cli_path
        table.add_row(
            result.agent,
            f"[{_status_style(result.status)}]{result.status}[/{_status_style(result.status)}]",
            _version_text(result.before_version, result.after_version) if result.status != "skipped" else "-",
            note,
        )
    console.print(table)
    console.print()
    console.print(f"Summary: {_succeeded(results)} succeeded, {_skipped(results)} skipped, {_failed(results)} failed.")
    if _found_cli_count(results) == 0:
        console.print("No plugin action was attempted because no supported agent CLI was found.")
    failed_results = [result for result in results if result.status == "failed"]
    if failed_results:
        console.print()
        console.print("[red]Failed agents:[/red]")
        for result in failed_results:
            command = " ".join(result.failed_command or [])
            detail = command or result.note
            console.print(f"  {result.agent}: {detail}")


def _print_install_results(results: list[InstallResult], console: Console) -> None:
    _print_action_results(results, console, title="Bark Agent Hook install")
    console.print()
    _print_install_next_steps(results, console)


def _print_uninstall_results(results: list[InstallResult], console: Console) -> None:
    _print_action_results(results, console, title="Bark Agent Hook uninstall")
    console.print()
    console.print("Marketplace sources, environment variables, and historical audit logs were left unchanged.")


def _print_install_next_steps(results: list[InstallResult], console: Console) -> None:
    if _found_cli_count(results) == 0:
        console.print("[bold]Next steps:[/bold]")
        console.print("  Install Codex, Claude Code, or OpenClaw first, then run:")
        console.print("  bark-agent-hook install")
        console.print()
        console.print("  Set BARK_DEVICE_KEY=<your Bark device key> before testing notifications.")
        return
    console.print("[bold]Next steps:[/bold]")
    console.print("  Set BARK_DEVICE_KEY=<your Bark device key>")
    console.print("  Optional: BARK_SERVER=https://api.day.app")
    console.print("  Optional: BARK_GROUP=<fixed Bark group>")
    console.print("  Optional: AGENT_BARK_NOTIFY_GROUP_MODE=agent|project|project-branch")
    console.print("  Optional: AGENT_BARK_NOTIFY_HOOK_URL=  # empty by default; optional click URL template")
    console.print("  Example: AGENT_BARK_NOTIFY_HOOK_URL=https://lody.ai/users/{LODY_ELECTRON_SESSION_USER_ID}/sessions/{LODY_SESSION_ID}")
    console.print("  Optional: AGENT_BARK_NOTIFY_AUDIT_LOG=1")
    console.print("  Optional: AGENT_BARK_NOTIFY_AUDIT_LOG_FILE=~/.bark-agent-hook/bark-agent-hook.log")
    console.print()
    if any(result.agent == "Codex" for result in results):
        console.print()
        console.print("[bold]Codex note:[/bold]")
        console.print("  If Codex runs hooks in a restricted shell/sandbox, set these variables in the environment inherited by Codex hook commands.")
    if any(result.agent == "OpenClaw" for result in results):
        console.print()
        console.print("[bold]OpenClaw note:[/bold]")
        console.print("  If OpenClaw Gateway runs as a service, set these variables in its wrapper/launchd/systemd/schtasks environment, then restart the gateway.")
    if any(result.agent == "OpenClaw" and result.status == "failed" and "Missing local plugin directory" in result.note for result in results):
        console.print()
        console.print("OpenClaw install currently requires the local plugin directory from the bark-agent-hook source checkout.")
        console.print("Run from the source checkout, or add packaged/remote OpenClaw plugin support in a follow-up.")
