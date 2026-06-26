from __future__ import annotations

import hashlib
from typing import Any


def _payload_value(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None or isinstance(value, dict | list):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _hash_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _hook_event_name(payload: dict[str, Any]) -> str | None:
    value = payload.get("hook_event_name") or payload.get("event") or payload.get("event_name") or payload.get("type")
    return str(value) if value is not None else None


def _env_value(env: dict[str, str], key: str, default: str = "") -> str:
    value = env.get(key, default).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value
