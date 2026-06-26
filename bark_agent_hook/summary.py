from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from bark_agent_hook.constants import BEARER_RE, FENCED_CODE_RE, MAX_TRANSCRIPT_BYTES, SENSITIVE_ASSIGNMENT_RE, SENSITIVE_KEY_RE, SHELL_PREFIX_RE

def _strip_url_query(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        split = urlsplit(raw_url)
        return urlunsplit((split.scheme, split.netloc, split.path, "", split.fragment))

    return re.sub(r"https?://[^\s<>'\")]+", replace, value)


def _redact_url(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        split = urlsplit(raw_url)
        return urlunsplit((split.scheme, split.netloc, "/[REDACTED]", "", ""))

    return re.sub(r"https?://[^\s<>'\")]+", replace, value)


def _extract_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_extract_text(item) for item in value]
        return " ".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("text", "content", "message"):
            text = _extract_text(value.get(key))
            if text:
                return text
    return None


def _extract_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _looks_like_raw_json(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
        return True
    return stripped.count('":') >= 3 and stripped.count("{") + stripped.count("[") >= 1


def _truncate_summary(text: str, max_chars: int) -> str:
    limit = max(1, max_chars)
    if len(text) <= limit:
        return text
    if limit == 1:
        return "…"
    return f"{text[: limit - 1].rstrip()}…"


def clean_summary_text(text: str | None, max_chars: int) -> str | None:
    if not text:
        return None
    body = FENCED_CODE_RE.sub(" ", text)
    body = BEARER_RE.sub("Bearer [REDACTED]", body)
    body = SENSITIVE_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", body)
    body = _strip_url_query(body)
    body = " ".join(body.split())
    body = body.strip("` \t\r\n")
    if not body or _looks_like_raw_json(body):
        return None
    if SENSITIVE_KEY_RE.search(body) and "[REDACTED]" not in body:
        return None
    return _truncate_summary(body, max_chars)


def _assistant_text_from_transcript_item(item: dict[str, Any]) -> str | None:
    role = str(item.get("role") or "").lower()
    item_type = str(item.get("type") or "").lower()
    message = item.get("message")
    if isinstance(message, dict):
        role = str(message.get("role") or role).lower()
        if role == "assistant":
            return _extract_text(message.get("content"))
    if role == "assistant":
        return _extract_text(item.get("content") or item.get("text") or item.get("message"))
    if item_type in {"assistant", "final", "assistant_message"}:
        return _extract_text(item.get("content") or item.get("text") or item.get("message"))
    return None


def _read_transcript_messages(transcript_path: str | None) -> list[str]:
    if not transcript_path:
        return []
    path = Path(transcript_path)
    if not path.is_file():
        return []
    try:
        raw = path.read_bytes()[:MAX_TRANSCRIPT_BYTES].decode(errors="replace")
    except OSError:
        return []

    messages: list[str] = []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                text = _assistant_text_from_transcript_item(item)
                if text:
                    messages.append(text)
        return messages
    if isinstance(value, dict):
        for key in ("messages", "items", "events"):
            nested = value.get(key)
            if isinstance(nested, list):
                for item in nested:
                    if isinstance(item, dict):
                        text = _assistant_text_from_transcript_item(item)
                        if text:
                            messages.append(text)
                return messages
        text = _assistant_text_from_transcript_item(value)
        return [text] if text else []

    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            text = _assistant_text_from_transcript_item(item)
            if text:
                messages.append(text)
    return messages


def _safe_tool_detail(tool_input: dict[str, Any]) -> str | None:
    for key in ("path", "file_path", "file", "cwd", "workspace", "project_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("command", "cmd"):
        value = tool_input.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        command = " ".join(value.split())
        if len(command) > 80 or SENSITIVE_KEY_RE.search(command):
            return None
        if SHELL_PREFIX_RE.search(command):
            return None
        return command
    return None


def _approval_tool_summary(tool_name: str | None, detail: str | None, max_chars: int) -> str | None:
    if not tool_name and not detail:
        return None
    if tool_name and detail:
        return clean_summary_text(f"{tool_name} 需要审批：{detail}", max_chars)
    if tool_name:
        return clean_summary_text(f"{tool_name} 需要审批", max_chars)
    return clean_summary_text(f"需要审批：{detail}", max_chars)


def extract_summary(runtime: str, event: str, payload: dict[str, Any], max_chars: int) -> str | None:
    if event == "completion":
        for candidate in (
            _extract_text(payload.get("last_assistant_message")),
            _extract_text(payload.get("lastAssistantMessage")),
            _extract_text(payload.get("content")),
            _extract_text(payload.get("message")),
            _extract_text(payload.get("summary")),
            _extract_text(payload.get("error")),
            *reversed(_read_transcript_messages(_extract_text(payload.get("transcript_path")))),
            *reversed(_read_transcript_messages(_extract_text(payload.get("transcriptPath")))),
        ):
            summary = clean_summary_text(candidate, max_chars)
            if summary:
                return summary
        return None

    if event == "approval_needed":
        tool_input = _extract_dict(payload.get("tool_input"))
        if not tool_input:
            tool_input = _extract_dict(payload.get("params"))
        require_approval = _extract_dict(payload.get("requireApproval"))
        approval = _extract_dict(payload.get("approval"))
        for candidate in (
            _extract_text(require_approval.get("description")),
            _extract_text(approval.get("description")),
            _extract_text(payload.get("description")),
            _extract_text(payload.get("title")),
        ):
            summary = clean_summary_text(candidate, max_chars)
            if summary:
                return summary
        description = clean_summary_text(_extract_text(tool_input.get("description")), max_chars)
        if description:
            return description
        tool_name = _extract_text(payload.get("tool_name") or payload.get("toolName"))
        detail = _safe_tool_detail(tool_input)
        summary = _approval_tool_summary(tool_name, detail, max_chars)
        if summary:
            return summary
        message = clean_summary_text(_extract_text(payload.get("message")), max_chars)
        if message:
            return message
        return None

    return None


def _normalized_payload_text(value: Any) -> str:
    return " ".join((_extract_text(value) or "").split()).strip()
