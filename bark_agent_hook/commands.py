import json
import os

import httpx
import typer
from rich.console import Console

from bark_agent_hook.app import cmd
from bark_agent_hook.audit import _finish_audit_record, _new_audit_record
from bark_agent_hook.constants import DEFAULT_SUMMARY_MAX_CHARS
from bark_agent_hook.installer import _install_for_available_agents, _uninstall_for_available_agents
from bark_agent_hook.models import AgentOption, Event, GroupModeOption, Runtime, SummaryMode
from bark_agent_hook.notification import already_sent, build_notification, resolve_group_mode, send_bark, skip_notification_reason
from bark_agent_hook.output import _found_cli_count, _print_install_results, _print_uninstall_results, _succeeded
from bark_agent_hook.runtime import _read_stdin, detect_event, detect_runtime, parse_hook_payload
from bark_agent_hook.settings import LodySettings
from bark_agent_hook.summary import extract_summary


@cmd.command()
def install(
    agents: list[AgentOption] | None = typer.Option(None, "--agent", help="Agent plugin to install. Repeat for multiple agents. Defaults to all supported agents."),
) -> None:
    """Install bark-agent-hook plugins for locally available agents.

    This command checks for codex, claude, and openclaw CLIs in PATH unless
    one or more --agent options are passed. Missing CLIs are skipped.

    Installed plugins:
      Codex:        bark-agent-hook-codex@bark-agent-hook
      Claude Code:  bark-agent-hook@bark-agent-hook --scope user
      OpenClaw:     local linked plugin from plugins/bark-agent-hook-openclaw
    """
    results = _install_for_available_agents(agents)
    _print_install_results(results, Console(highlight=False, width=120))
    if _found_cli_count(results) > 0 and _succeeded(results) == 0:
        raise typer.Exit(1)


@cmd.command()
def uninstall(
    agents: list[AgentOption] | None = typer.Option(None, "--agent", help="Agent plugin to uninstall. Repeat for multiple agents. Defaults to all supported agents."),
) -> None:
    """Uninstall bark-agent-hook plugins for locally available agents."""
    results = _uninstall_for_available_agents(agents)
    _print_uninstall_results(results, Console(highlight=False, width=120))
    if _found_cli_count(results) > 0 and _succeeded(results) == 0:
        raise typer.Exit(1)


@cmd.command()
def hook(
    runtime: Runtime = typer.Option("auto", "--runtime", help="Hook runtime: codex, claude, openclaw, or auto."),
    event: Event = typer.Option("auto", "--event", help="Notification event override."),
    message: str | None = typer.Option(None, "--message", help="Override short notification body."),
    group_mode: GroupModeOption | None = typer.Option(None, "--group-mode", help="Bark group mode: agent, project, or project-branch."),
    summary_mode: SummaryMode = typer.Option("fixed", "--summary-mode", help="Notification summary mode: fixed or extract."),
    summary_max_chars: int = typer.Option(DEFAULT_SUMMARY_MAX_CHARS, "--summary-max-chars", min=1, help="Maximum extractive summary length."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print notification summary without sending Bark request."),
    no_dedupe: bool = typer.Option(False, "--no-dedupe", help="Disable duplicate suppression."),
) -> None:
    """Read hook JSON from stdin and send a best-effort Bark notification."""
    env = dict(os.environ)
    payload = parse_hook_payload(_read_stdin())
    lody_settings = LodySettings()
    resolved_runtime = detect_runtime(runtime, env, payload, lody_settings)
    resolved_event = detect_event(event, payload)
    resolved_group_mode = resolve_group_mode(group_mode, env)
    audit_record = _new_audit_record(runtime=resolved_runtime, event=resolved_event, payload=payload, summary_mode=summary_mode, lody_settings=lody_settings)
    try:
        if resolved_event is None:
            _finish_audit_record(env, audit_record, status="skipped_unsupported_event")
            if dry_run:
                typer.echo("skip: unsupported hook event")
            return

        resolved_message = message
        if resolved_message is None and summary_mode == "extract":
            resolved_message = extract_summary(resolved_runtime, resolved_event, payload, summary_max_chars)

        skip_reason = skip_notification_reason(resolved_runtime, resolved_event, payload, resolved_message)
        if skip_reason is not None:
            _finish_audit_record(env, audit_record, status=skip_reason)
            if dry_run:
                typer.echo("skip: OpenClaw event has no deliverable reply")
            return

        notification = build_notification(
            runtime=resolved_runtime,
            event=resolved_event,
            message=resolved_message,
            env=env,
            payload=payload,
            lody_settings=lody_settings,
            group_mode=resolved_group_mode,
        )
        if notification is None:
            _finish_audit_record(env, audit_record, status="skipped_missing_device_key")
            if dry_run:
                typer.echo("skip: BARK_DEVICE_KEY is missing")
            return

        if not no_dedupe and already_sent(notification.dedupe_key, env):
            _finish_audit_record(env, audit_record, status="skipped_duplicate", notification=notification)
            if dry_run:
                typer.echo("skip: duplicate notification")
            return

        if dry_run:
            _finish_audit_record(env, audit_record, status="sent", notification=notification)
            output = {"title": notification.title, "body": notification.body, "icon": notification.icon_url, "group": notification.group, "url": notification.bark_url}
            if notification.click_url:
                output["click_url"] = notification.click_url
            typer.echo(json.dumps(output, ensure_ascii=False))
            return

        try:
            send_bark(notification)
        except httpx.HTTPError as e:
            _finish_audit_record(env, audit_record, status="bark_http_error", notification=notification, error=e)
            typer.echo(f"Bark notification failed: {e}", err=True)
            return
        _finish_audit_record(env, audit_record, status="sent", notification=notification)
    except Exception as e:
        _finish_audit_record(env, audit_record, status="hook_exception", error=e)
        typer.echo(f"Bark hook failed: {e}", err=True)
        return
