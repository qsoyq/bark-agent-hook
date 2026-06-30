from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import typer

from bark_agent_hook.constants import (
    CLAUDE_CODE_ICON_URL,
    CODEX_ICON_URL,
    DEFAULT_MESSAGES,
    EVENT_LABELS,
    LODY_ICON_URL,
    MAX_MESSAGE_LENGTH,
    OPENCLAW_ICON_URL,
)
from bark_agent_hook.models import AgentIdentity, Event, Runtime
from bark_agent_hook.settings import LodySettings

USER_INPUT_TOOL_NAMES = {"request_user_input", "functions.request_user_input"}
TOOL_CALL_EVENT_NAMES = {"ToolCall", "tool_call", "FunctionCall", "function_call", "FunctionCallOutput", "function_call_output", "tool_call_output"}


def _read_stdin() -> str:
    try:
        return typer.get_text_stream("stdin").read()
    except OSError:
        return ""


def parse_hook_payload(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def detect_identity(env: dict[str, str], lody_settings: LodySettings) -> AgentIdentity:
    if lody_settings.has_lody_signal() or env.get("__CFBundleIdentifier") == "ai.lody.desktop":
        return AgentIdentity("Lody", LODY_ICON_URL)
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE") or env.get("CLAUDE_PROJECT_DIR") or env.get("CLAUDE_CONFIG_DIR"):
        return AgentIdentity("Claude Code", CLAUDE_CODE_ICON_URL)
    return AgentIdentity("Codex", CODEX_ICON_URL)


def identity_for_runtime(runtime: str, env: dict[str, str], lody_settings: LodySettings) -> AgentIdentity:
    if runtime == "openclaw":
        return AgentIdentity("OpenClaw", OPENCLAW_ICON_URL)
    if runtime == "claude":
        return AgentIdentity("Claude Code", CLAUDE_CODE_ICON_URL)
    if runtime == "codex":
        return AgentIdentity("Codex", CODEX_ICON_URL)
    return detect_identity(env, lody_settings)


def detect_runtime(runtime: Runtime, env: dict[str, str], payload: dict[str, Any], lody_settings: LodySettings) -> str:
    if runtime != "auto":
        return runtime
    if lody_settings.has_lody_signal() or env.get("__CFBundleIdentifier") == "ai.lody.desktop":
        return "lody"
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE") or env.get("CLAUDE_PROJECT_DIR") or env.get("CLAUDE_CONFIG_DIR"):
        return "claude"
    if env.get("OPENCLAW_SESSION_ID") or env.get("OPENCLAW_WORKSPACE_DIR") or env.get("OPENCLAW_GATEWAY_PORT"):
        return "openclaw"
    if env.get("CODEX_CI") or env.get("CODEX_THREAD_ID"):
        return "codex"
    payload_hint = f"{payload.get('runtime') or ''} {payload.get('source') or ''}".lower()
    if "claude" in payload_hint:
        return "claude"
    if "codex" in payload_hint:
        return "codex"
    if "openclaw" in payload_hint:
        return "openclaw"
    return "codex"


def detect_event(event: Event, payload: dict[str, Any]) -> str | None:
    if event != "auto":
        return event

    hook_event = str(payload.get("hook_event_name") or payload.get("event") or payload.get("event_name") or payload.get("type") or "")
    hook_event_lower = hook_event.lower()
    if hook_event in {"PermissionRequest", "approval_needed", "approval-needed", "approval:needed", "before_tool_call"}:
        return "approval_needed"
    if hook_event == "PreToolUse":
        tool_name = str(payload.get("tool_name") or payload.get("toolName") or payload.get("tool") or payload.get("name") or "")
        if tool_name == "AskUserQuestion" or tool_name in USER_INPUT_TOOL_NAMES:
            return "approval_needed"
        return "audit_only"
    if hook_event == "PostToolUse" or hook_event in TOOL_CALL_EVENT_NAMES:
        return "audit_only"
    if payload.get("success") is False and hook_event not in {"PermissionDenied"}:
        return "failed"
    if hook_event in {"Elicitation", "PermissionDenied"}:
        return "attention_needed"
    if hook_event in {"plan_update", "plan_delta", "turn/plan/updated", "TurnPlanUpdatedNotification", "PlanDeltaNotification"}:
        return "attention_needed"
    if hook_event in {"agent_end", "agent:end"}:
        return "completion" if payload.get("success") is not False else "failed"
    if hook_event in {"message_sent", "message:sent"}:
        return "completion" if payload.get("success") is not False else "failed"
    if hook_event == "Notification":
        message = str(payload.get("message") or payload.get("notification_type") or payload.get("reason") or "")
        if "permission" in message.lower() or "approval" in message.lower():
            return "approval_needed"
        return "attention_needed"
    if hook_event in {"Stop", "SubagentStop"}:
        return "completion"
    if hook_event == "StopFailure":
        return "failed"
    if hook_event == "SessionEnd" and str(payload.get("reason") or payload.get("status") or "").lower() in {"failed", "error"}:
        return "failed"
    if hook_event in {"MessageDisplay", "UserPromptSubmit", "SessionStart", "SubagentStart", "PreCompact", "PostCompact"}:
        return "audit_only"
    if "plan" in hook_event_lower and ("update" in hook_event_lower or "delta" in hook_event_lower):
        return "attention_needed"
    return None


def project_name(payload: dict[str, Any], cwd: Path | None = None) -> str:
    for key in ("project_name", "workspace_name", "repository", "repo", "agentId", "agent_id", "name"):
        raw_name = payload.get(key)
        if isinstance(raw_name, str) and raw_name.strip():
            return raw_name.strip()

    env = os.environ
    for key in ("AGENT_BARK_NOTIFY_PROJECT_NAME", "OPENCLAW_WORKSPACE_NAME", "CODEX_WORKSPACE_NAME", "CODEX_PROJECT_NAME", "LODY_WORKSPACE_NAME", "LODY_PROJECT_NAME"):
        raw_name = env.get(key)
        if raw_name and raw_name.strip():
            return raw_name.strip()

    raw = payload.get("cwd") or payload.get("workspace") or payload.get("workspaceDir") or payload.get("project_path")
    if isinstance(raw, str) and raw:
        return Path(raw).name
    return (cwd or Path.cwd()).name


def _path_from_payload(payload: dict[str, Any], cwd: Path | None = None) -> Path:
    for key in ("cwd", "workspace", "workspaceDir", "workspace_dir", "project_path"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw:
            return Path(raw)
    return cwd or Path.cwd()


def cwd_basename(payload: dict[str, Any], cwd: Path | None = None) -> str:
    return _path_from_payload(payload, cwd).name


def branch_name(payload: dict[str, Any], env: dict[str, str], cwd: Path | None = None) -> str:
    for key in ("branch_name", "branch", "git_branch", "ref_name"):
        raw_name = payload.get(key)
        if isinstance(raw_name, str) and raw_name.strip():
            return raw_name.strip().removeprefix("refs/heads/")

    for key in ("AGENT_BARK_NOTIFY_BRANCH_NAME", "CODEX_BRANCH_NAME", "GIT_BRANCH", "BRANCH_NAME"):
        raw_name = env.get(key)
        if raw_name and raw_name.strip():
            return raw_name.strip().removeprefix("refs/heads/")

    repo_path = _path_from_payload(payload, cwd)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "branch", "--show-current"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _explicit_project_name(payload: dict[str, Any], env: dict[str, str], *, include_agent_id: bool) -> str:
    keys = ["project_name", "workspace_name", "repository", "repo"]
    if include_agent_id:
        keys.extend(["agentId", "agent_id", "name"])
    for key in keys:
        raw_name = payload.get(key)
        if isinstance(raw_name, str) and raw_name.strip():
            return raw_name.strip()

    env_keys = [
        "AGENT_BARK_NOTIFY_PROJECT_NAME",
        "OPENCLAW_WORKSPACE_NAME",
        "CODEX_WORKSPACE_NAME",
        "CODEX_PROJECT_NAME",
        "LODY_WORKSPACE_NAME",
        "LODY_PROJECT_NAME",
    ]
    for key in env_keys:
        raw_name = env.get(key)
        if raw_name and raw_name.strip():
            return raw_name.strip()
    return ""


def title_project_name(runtime: str, payload: dict[str, Any], env: dict[str, str], cwd: Path | None = None) -> str:
    if runtime == "openclaw":
        return _explicit_project_name(payload, env, include_agent_id=False)
    return project_name(payload, cwd)


def title_branch_name(runtime: str, payload: dict[str, Any], env: dict[str, str], cwd: Path | None = None) -> str:
    if runtime != "openclaw":
        return branch_name(payload, env, cwd)

    for key in ("branch_name", "branch", "git_branch", "ref_name"):
        raw_name = payload.get(key)
        if isinstance(raw_name, str) and raw_name.strip():
            return raw_name.strip().removeprefix("refs/heads/")

    for key in ("AGENT_BARK_NOTIFY_BRANCH_NAME", "CODEX_BRANCH_NAME", "GIT_BRANCH", "BRANCH_NAME"):
        raw_name = env.get(key)
        if raw_name and raw_name.strip():
            return raw_name.strip().removeprefix("refs/heads/")
    return ""


def session_name(payload: dict[str, Any], env: dict[str, str]) -> str:
    for key in ("session_name", "conversation_name", "thread_name", "workspace_session_name"):
        raw_name = payload.get(key)
        if isinstance(raw_name, str) and raw_name.strip():
            return raw_name.strip()

    for key in ("AGENT_BARK_NOTIFY_SESSION_NAME", "OPENCLAW_SESSION_NAME", "CODEX_SESSION_NAME", "LODY_SESSION_NAME"):
        raw_name = env.get(key)
        if raw_name and raw_name.strip():
            return raw_name.strip()
    return ""


def safe_message(event: str, message: str | None) -> str:
    body = (message or DEFAULT_MESSAGES.get(event) or "任务状态已更新").strip()
    body = body.replace("\n", " ")
    if len(body) > MAX_MESSAGE_LENGTH:
        return f"{body[: MAX_MESSAGE_LENGTH - 1]}…"
    return body


def event_label(event: str) -> str:
    return EVENT_LABELS.get(event, "Update")
