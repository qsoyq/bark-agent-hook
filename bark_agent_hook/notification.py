from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path
from typing import Any, TypeGuard
from urllib.parse import quote

import httpx
import typer

from bark_agent_hook.constants import (
    DEDUP_TTL_SECONDS,
    GROUP_MODE_CHOICES,
    GROUP_MODE_ENV,
    HOOK_URL_TEMPLATE_ENV,
    TITLE_TEMPLATE_ENV,
)
from bark_agent_hook.models import AgentIdentity, GroupMode, GroupModeOption, Notification
from bark_agent_hook.runtime import (
    branch_name,
    cwd_basename,
    event_label,
    identity_for_runtime,
    project_name,
    safe_message,
    session_name,
    title_branch_name,
    title_project_name,
)
from bark_agent_hook.settings import LodySettings
from bark_agent_hook.summary import _normalized_payload_text
from bark_agent_hook.utils import _env_value, _hook_event_name, _payload_value


class _SafeTemplateVars(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _default_title(values: dict[str, str]) -> str:
    event = " ".join(values.get("event", "").split())
    project = " ".join(values.get("project", "").split())
    if event and project:
        return f"{event} - {project}"
    return event or project


def notification_title(*, runtime: str, identity: AgentIdentity, event: str, payload: dict[str, Any], env: dict[str, str], lody_settings: LodySettings, cwd: Path | None = None) -> str:
    values = _SafeTemplateVars(
        agent=identity.name,
        event=event_label(event),
        project=title_project_name(runtime, payload, env, cwd),
        runtime=runtime,
        cwd_basename=cwd_basename(payload, cwd),
        branch=title_branch_name(runtime, payload, env, cwd),
        session=session_name(payload, env),
    )
    values.update(lody_settings.template_values())
    configured_template = env.get(TITLE_TEMPLATE_ENV, "").strip()
    if not configured_template:
        title = _default_title(values)
        return title or _default_title(_SafeTemplateVars(agent=identity.name, event=event_label(event)))
    try:
        title = configured_template.format_map(values)
    except ValueError:
        title = _default_title(values)
    return " ".join(title.split()) or _default_title(values)


def _encoded_hook_url_vars(
    *,
    runtime: str,
    identity: AgentIdentity,
    event: str,
    payload: dict[str, Any],
    env: dict[str, str],
    lody_settings: LodySettings,
    cwd: Path | None = None,
) -> dict[str, str]:
    values = {
        "runtime": runtime,
        "agent": identity.name,
        "event": event,
        "project": project_name(payload, cwd),
        "branch": branch_name(payload, env, cwd),
        "session": session_name(payload, env),
        "session_id": _payload_value(payload, "session_id", "sessionId"),
        "session_key": _payload_value(payload, "session_key", "sessionKey"),
        "conversation_id": _payload_value(payload, "conversation_id", "conversationId"),
        "message_id": _payload_value(payload, "message_id", "messageId"),
        "run_id": _payload_value(payload, "run_id", "runId"),
        "agent_id": _payload_value(payload, "agent_id", "agentId"),
        "workspace_dir": _payload_value(payload, "workspace_dir", "workspaceDir", "workspace", "cwd", "project_path"),
        "cwd_basename": cwd_basename(payload, cwd),
    }
    values.update(lody_settings.template_values())
    return {key: quote(value, safe="") for key, value in values.items()}


def hook_click_url(
    *,
    runtime: str,
    identity: AgentIdentity,
    event: str,
    payload: dict[str, Any],
    env: dict[str, str],
    lody_settings: LodySettings,
    cwd: Path | None = None,
) -> str | None:
    configured_template = _env_value(env, HOOK_URL_TEMPLATE_ENV)
    if not configured_template:
        return None
    try:
        rendered = configured_template.format_map(_encoded_hook_url_vars(runtime=runtime, identity=identity, event=event, payload=payload, env=env, lody_settings=lody_settings, cwd=cwd))
    except (KeyError, ValueError):
        return None
    rendered = rendered.strip()
    return rendered or None


def _is_group_mode(value: str) -> TypeGuard[GroupMode]:
    return value in GROUP_MODE_CHOICES


def _group_mode_error(value: str) -> typer.BadParameter:
    choices = ", ".join(GROUP_MODE_CHOICES)
    return typer.BadParameter(f"{GROUP_MODE_ENV} must be one of: {choices}; got {value!r}")


def resolve_group_mode(cli_group_mode: GroupModeOption | None, env: dict[str, str]) -> GroupMode:
    if cli_group_mode is not None:
        value = cli_group_mode.value
        if _is_group_mode(value):
            return value
        raise _group_mode_error(value)

    env_value = _env_value(env, GROUP_MODE_ENV)
    if not env_value:
        return "agent"
    if _is_group_mode(env_value):
        return env_value
    raise _group_mode_error(env_value)


def notification_group(
    *,
    runtime: str,
    identity: AgentIdentity,
    event: str,
    payload: dict[str, Any],
    env: dict[str, str],
    lody_settings: LodySettings,
    group_mode: GroupMode,
    cwd: Path | None = None,
) -> str | None:
    configured_group = _env_value(env, "BARK_GROUP")
    if configured_group:
        values = _SafeTemplateVars(
            agent=identity.name,
            event=event_label(event),
            project=project_name(payload, cwd),
            runtime=runtime,
            cwd_basename=cwd_basename(payload, cwd),
            branch=branch_name(payload, env, cwd),
            session=session_name(payload, env),
        )
        values.update(lody_settings.template_values())
        try:
            rendered = configured_group.format_map(values)
        except ValueError:
            return configured_group
        return " ".join(rendered.split()) or None

    if group_mode == "agent":
        return identity.name

    project = project_name(payload, cwd).strip()
    if group_mode == "project":
        return project or identity.name

    if not project:
        return identity.name
    branch = branch_name(payload, env, cwd).strip()
    if not branch:
        return project
    return f"{project}@{branch}"


def _markdown_value(value: str) -> str:
    return " ".join(value.split()).replace("`", "'")


def _markdown_code(value: str) -> str:
    return f"`{_markdown_value(value)}`"


def notification_markdown(
    *,
    runtime: str,
    identity: AgentIdentity,
    event: str,
    payload: dict[str, Any],
    env: dict[str, str],
    body: str,
    group: str | None,
    cwd: Path | None = None,
) -> str:
    lines = [
        f"## {_markdown_value(event_label(event))} · {_markdown_value(identity.name)}",
        "",
        f"> {_markdown_value(body)}",
        "",
        f"- Project: {_markdown_code(project_name(payload, cwd))}",
    ]
    branch = branch_name(payload, env, cwd).strip()
    if branch:
        lines.append(f"- Branch: {_markdown_code(branch)}")
    session = session_name(payload, env).strip()
    if session:
        lines.append(f"- Session: {_markdown_code(session)}")
    lines.append(f"- Runtime: {_markdown_code(runtime)}")
    cwd_name = cwd_basename(payload, cwd).strip()
    if cwd_name and cwd_name != project_name(payload, cwd).strip():
        lines.append(f"- Workspace: {_markdown_code(cwd_name)}")
    if group:
        lines.append(f"- Group: {_markdown_code(group)}")
    return "\n".join(lines)


def _is_no_reply_text(text: str | None) -> bool:
    return bool(text and text.strip().upper() == "NO_REPLY")


def _openclaw_payload_is_no_reply(payload: dict[str, Any], message: str | None) -> bool:
    if _is_no_reply_text(message):
        return True
    for key in ("content", "message", "summary", "last_assistant_message", "lastAssistantMessage"):
        if _is_no_reply_text(_normalized_payload_text(payload.get(key))):
            return True
    return False


def _openclaw_has_reply_context(payload: dict[str, Any], message: str | None) -> bool:
    if message and not _is_no_reply_text(message):
        return True
    for key in ("content", "message", "summary", "last_assistant_message", "lastAssistantMessage"):
        text = _normalized_payload_text(payload.get(key))
        if text and not _is_no_reply_text(text):
            return True
    for key in ("messageId", "message_id", "conversationId", "conversation_id", "channelId", "channel_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _openclaw_has_failure_context(payload: dict[str, Any]) -> bool:
    for key in ("error", "reason", "status", "failureReason", "failure_reason"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, dict) and any(value.values()):
            return True
    for key in ("messageId", "message_id", "conversationId", "conversation_id", "channelId", "channel_id", "channel"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def skip_notification_reason(runtime: str, event: str, payload: dict[str, Any], message: str | None) -> str | None:
    if runtime != "openclaw":
        return None
    if _openclaw_payload_is_no_reply(payload, message):
        return "skipped_openclaw_no_reply"

    hook_event = _hook_event_name(payload)
    if hook_event not in {"agent_end", "agent:end"}:
        return None
    if event == "completion" and not _openclaw_has_reply_context(payload, message):
        return "skipped_openclaw_silent_agent_end"
    if event == "failed" and not _openclaw_has_failure_context(payload):
        return "skipped_openclaw_silent_agent_end"
    return None


def build_dedupe_key(runtime: str, event: str, payload: dict[str, Any], body: str) -> str:
    session = payload.get("session_id") or payload.get("sessionId") or payload.get("sessionKey") or payload.get("conversation_id") or payload.get("transcript_path") or ""
    stable_payload = {
        "hook_event_name": payload.get("hook_event_name") or payload.get("event") or payload.get("event_name") or payload.get("type"),
        "session_id": session,
        "message_id": payload.get("messageId") or payload.get("message_id"),
        "conversation_id": payload.get("conversationId") or payload.get("conversation_id"),
        "tool_name": payload.get("tool_name") or payload.get("toolName"),
        "cwd": payload.get("cwd") or payload.get("workspaceDir"),
        "body": body,
    }
    digest = hashlib.sha256(json.dumps(stable_payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    return f"{runtime}:{event}:{session}:{digest}"


def _dedupe_dir(env: dict[str, str]) -> Path:
    base = _env_value(env, "AGENT_BARK_NOTIFY_STATE_DIR")
    if base:
        return Path(base)
    return Path(tempfile.gettempdir()) / "bark-agent-hook"


def already_sent(dedupe_key: str, env: dict[str, str], *, now: float | None = None) -> bool:
    now = now if now is not None else time.time()
    state_dir = _dedupe_dir(env)
    state_dir.mkdir(parents=True, exist_ok=True)
    for path in state_dir.iterdir():
        try:
            if now - path.stat().st_mtime > DEDUP_TTL_SECONDS:
                path.unlink()
        except OSError:
            continue
    path = state_dir / hashlib.sha256(dedupe_key.encode()).hexdigest()
    if path.exists():
        return True
    path.write_text(str(int(now)))
    return False


def should_dedupe_notification(runtime: str, event: str, payload: dict[str, Any]) -> bool:
    if event == "approval_needed":
        return False
    return True


def build_notification(
    *,
    runtime: str,
    event: str,
    message: str | None,
    env: dict[str, str],
    payload: dict[str, Any],
    lody_settings: LodySettings,
    group_mode: GroupMode = "agent",
    cwd: Path | None = None,
) -> Notification | None:
    device_key = _env_value(env, "BARK_DEVICE_KEY")
    if not device_key:
        return None

    identity = identity_for_runtime(runtime, env, lody_settings)
    body = safe_message(event, message)
    title = notification_title(runtime=runtime, identity=identity, event=event, payload=payload, env=env, lody_settings=lody_settings, cwd=cwd)
    bark_server = _env_value(env, "BARK_SERVER", "https://api.day.app")
    dedupe_key = build_dedupe_key(runtime, event, payload, body)
    group = notification_group(runtime=runtime, identity=identity, event=event, payload=payload, env=env, lody_settings=lody_settings, group_mode=group_mode, cwd=cwd)
    return Notification(
        title=title,
        body=body,
        markdown=notification_markdown(runtime=runtime, identity=identity, event=event, payload=payload, env=env, body=body, group=group, cwd=cwd),
        icon_url=identity.icon_url,
        group=group,
        bark_url=f"{bark_server.rstrip('/')}/{device_key}",
        click_url=hook_click_url(runtime=runtime, identity=identity, event=event, payload=payload, env=env, lody_settings=lody_settings, cwd=cwd),
        dedupe_key=dedupe_key,
    )


def send_bark(notification: Notification) -> None:
    data = {
        "title": notification.title,
        "icon": notification.icon_url,
    }
    if notification.markdown:
        data["markdown"] = notification.markdown
    else:
        data["body"] = notification.body
    if notification.group:
        data["group"] = notification.group
    if notification.click_url:
        data["url"] = notification.click_url
    with httpx.Client(timeout=10) as client:
        client.post(notification.bark_url, data=data).raise_for_status()
