from __future__ import annotations

import importlib.metadata
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bark_agent_hook.constants import (
    AUDIT_LOG_ENV,
    AUDIT_LOG_FILE_ENV,
    BEARER_RE,
    DEFAULT_AUDIT_LOG_PATH,
    SENSITIVE_ASSIGNMENT_RE,
)
from bark_agent_hook.models import Notification, SummaryMode
from bark_agent_hook.runtime import TOOL_CALL_EVENT_NAMES, project_name
from bark_agent_hook.settings import LodySettings
from bark_agent_hook.summary import _redact_url, _truncate_summary, clean_summary_text
from bark_agent_hook.utils import _env_value, _hash_value, _hook_event_name


def _session_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("session_id") or payload.get("sessionId") or payload.get("sessionKey") or payload.get("conversation_id") or payload.get("transcript_path")
    return str(value) if value is not None else None


def _payload_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _payload_text(payload: dict[str, Any], *keys: str) -> str | None:
    value = _payload_value(payload, *keys)
    if value is None or isinstance(value, dict | list):
        return None
    text = str(value).strip()
    return text or None


def _audit_enabled(env: dict[str, str]) -> bool:
    return _env_value(env, AUDIT_LOG_ENV).lower() in {"1", "true", "yes", "on"}


def _audit_log_path(env: dict[str, str]) -> Path:
    configured = _env_value(env, AUDIT_LOG_FILE_ENV)
    if configured:
        return Path(configured).expanduser()
    if sys.platform == "win32" and (home := env.get("HOME")):
        return Path(home).expanduser() / ".bark-agent-hook" / "bark-agent-hook.log"
    return DEFAULT_AUDIT_LOG_PATH.expanduser()


def _package_version(distribution_name: str = "bark-agent-hook") -> str | None:
    try:
        return importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _command_dir(argv0: str | None = None) -> str | None:
    command = argv0 if argv0 is not None else sys.argv[0]
    if not command:
        return None

    command_path = Path(command).expanduser()
    if command_path.name != command:
        try:
            return str(command_path.resolve().parent)
        except (OSError, RuntimeError):
            return None

    found = shutil.which(command)
    if found is None and sys.platform == "win32" and Path(command).suffix == "":
        for suffix in (".exe", ".cmd", ".bat"):
            found = shutil.which(f"{command}{suffix}")
            if found is not None:
                break
    if found is None:
        return None
    try:
        return str(Path(found).resolve().parent)
    except (OSError, RuntimeError):
        return None


def _safe_error_message(error: BaseException) -> str:
    message = " ".join(str(error).split())
    message = BEARER_RE.sub("Bearer [REDACTED]", message)
    message = SENSITIVE_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", message)
    message = _redact_url(message)
    return _truncate_summary(message, 200)


def _safe_body_preview(body: str) -> str | None:
    return clean_summary_text(body, 200)


def _safe_payload_preview(payload: dict[str, Any], *keys: str) -> str | None:
    return clean_summary_text(_payload_text(payload, *keys), 200)


def _tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    value = _payload_value(payload, "tool_input", "toolInput", "params", "input")
    return value if isinstance(value, dict) else {}


def _tool_input_summary(tool_input: dict[str, Any]) -> str | None:
    questions = tool_input.get("questions")
    if isinstance(questions, list):
        for item in questions:
            if not isinstance(item, dict):
                continue
            summary = clean_summary_text(_payload_text(item, "question", "title", "header"), 200)
            if summary:
                return summary

    for key in ("path", "file_path", "file", "cwd", "workspace", "project_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return clean_summary_text(value, 200)

    for key in ("description", "summary", "title", "message"):
        summary = clean_summary_text(_payload_text(tool_input, key), 200)
        if summary:
            return summary

    return None


def _tool_command_length(tool_input: dict[str, Any]) -> int | None:
    value = _payload_text(tool_input, "command", "cmd")
    if value is None:
        return None
    return len(value)


def _question_count(tool_input: dict[str, Any]) -> int | None:
    questions = tool_input.get("questions")
    if not isinstance(questions, list):
        return None
    return len([item for item in questions if isinstance(item, dict)])


def _exit_code(payload: dict[str, Any]) -> int | None:
    value = _payload_value(payload, "exit_code", "exitCode", "returncode", "return_code")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _tool_status(payload: dict[str, Any]) -> str | None:
    status = clean_summary_text(_payload_text(payload, "tool_status", "toolStatus"), 80)
    if status:
        return status
    success = payload.get("success")
    if success is True:
        return "success"
    if success is False:
        return "failed"
    return None


def _add_tool_metadata(record: dict[str, Any], payload: dict[str, Any]) -> None:
    hook_event = _hook_event_name(payload)
    tool_name = clean_summary_text(_payload_text(payload, "tool_name", "toolName", "tool", "name"), 120)
    tool_input = _tool_input(payload)
    if not tool_name and not tool_input and hook_event not in {"PreToolUse", "PostToolUse", "PermissionRequest", *TOOL_CALL_EVENT_NAMES}:
        return

    if tool_name:
        record["tool_name"] = tool_name

    tool_kind = clean_summary_text(_payload_text(payload, "tool_kind", "toolKind", "tool_type", "toolType", "kind"), 80)
    if tool_kind:
        record["tool_kind"] = tool_kind

    call_id = _payload_value(payload, "tool_call_id", "toolCallId", "call_id", "callId", "id")
    if call_id is not None:
        record["tool_call_id_hash"] = _hash_value(call_id)

    tool_status = _tool_status(payload)
    if tool_status:
        record["tool_status"] = tool_status

    exit_code = _exit_code(payload)
    if exit_code is not None:
        record["exit_code"] = exit_code

    command_length = _tool_command_length(tool_input)
    if command_length is not None:
        record["tool_command_len"] = command_length

    questions_count = _question_count(tool_input)
    if questions_count is not None:
        record["tool_question_count"] = questions_count

    input_summary = _tool_input_summary(tool_input)
    if input_summary:
        record["tool_input_summary"] = input_summary

    result_summary = _safe_payload_preview(payload, "summary", "reason", "error", "message")
    if result_summary:
        record["tool_result_summary"] = result_summary


def _write_audit_record(env: dict[str, str], record: dict[str, Any]) -> None:
    if not _audit_enabled(env):
        return
    try:
        path = _audit_log_path(env)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            f.write("\n")
    except OSError:
        return


def _new_audit_record(
    *,
    runtime: str,
    event: str | None,
    payload: dict[str, Any],
    summary_mode: SummaryMode,
    lody_settings: LodySettings,
    cwd: Path | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "runtime": runtime,
        "event": event,
        "bark_agent_hook_version": _package_version(),
        "command_dir": _command_dir(),
        "hook_event_name": _hook_event_name(payload),
        "status": None,
        "project": project_name(payload, cwd),
        "session_id_hash": _hash_value(_session_id(payload)),
        "dedupe_key_hash": None,
        "summary_mode": summary_mode,
        "title": None,
        "body_len": None,
    }
    lody_values = lody_settings.audit_values()
    if lody_values:
        record["lody"] = lody_values
    _add_tool_metadata(record, payload)
    return record


def _finish_audit_record(
    env: dict[str, str],
    record: dict[str, Any],
    *,
    status: str,
    notification: Notification | None = None,
    error: BaseException | None = None,
) -> None:
    record["status"] = status
    if notification is not None:
        record["dedupe_key_hash"] = _hash_value(notification.dedupe_key)
        record["title"] = notification.title
        record["body_len"] = len(notification.body)
        body_preview = _safe_body_preview(notification.body)
        if body_preview is not None:
            record["body_preview"] = body_preview
    if error is not None:
        record["error_class"] = error.__class__.__name__
        record["error_message"] = _safe_error_message(error)
    _write_audit_record(env, record)
