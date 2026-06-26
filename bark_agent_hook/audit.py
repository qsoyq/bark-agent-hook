from __future__ import annotations

import json
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
from bark_agent_hook.runtime import project_name
from bark_agent_hook.settings import LodySettings
from bark_agent_hook.summary import _redact_url, _truncate_summary, clean_summary_text
from bark_agent_hook.utils import _env_value, _hash_value, _hook_event_name


def _session_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("session_id") or payload.get("sessionId") or payload.get("sessionKey") or payload.get("conversation_id") or payload.get("transcript_path")
    return str(value) if value is not None else None


def _audit_enabled(env: dict[str, str]) -> bool:
    return _env_value(env, AUDIT_LOG_ENV).lower() in {"1", "true", "yes", "on"}


def _audit_log_path(env: dict[str, str]) -> Path:
    configured = _env_value(env, AUDIT_LOG_FILE_ENV)
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_AUDIT_LOG_PATH.expanduser()


def _safe_error_message(error: BaseException) -> str:
    message = " ".join(str(error).split())
    message = BEARER_RE.sub("Bearer [REDACTED]", message)
    message = SENSITIVE_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", message)
    message = _redact_url(message)
    return _truncate_summary(message, 200)


def _safe_body_preview(body: str) -> str | None:
    return clean_summary_text(body, 200)


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
