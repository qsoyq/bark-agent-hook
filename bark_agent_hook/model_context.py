from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from bark_agent_hook.utils import _env_value, _hash_value, _payload_value

MODEL_KEYS = ("model", "modelName", "model_name", "modelId", "model_id", "resolvedModel", "resolved_model")
PROVIDER_KEYS = ("provider", "modelProvider", "model_provider", "resolvedProvider", "resolved_provider")
SESSION_KEYS = ("session_id", "sessionId", "sessionKey", "conversation_id", "transcript_path")


def model_name(payload: dict[str, Any]) -> str:
    return _payload_value(payload, *MODEL_KEYS)


def provider_name(payload: dict[str, Any]) -> str:
    return _payload_value(payload, *PROVIDER_KEYS)


def model_display_name(payload: dict[str, Any]) -> str:
    model = model_name(payload)
    if not model:
        return ""
    provider = provider_name(payload)
    if not provider or model == provider or model.startswith(f"{provider}/"):
        return model
    return f"{provider}/{model}"


def _state_dir(env: dict[str, str]) -> Path:
    configured = _env_value(env, "AGENT_BARK_NOTIFY_STATE_DIR")
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "bark-agent-hook"


def _session_hash(payload: dict[str, Any]) -> str | None:
    return _hash_value(_payload_value(payload, *SESSION_KEYS))


def _cache_path(runtime: str, payload: dict[str, Any], env: dict[str, str]) -> Path | None:
    session_hash = _session_hash(payload)
    if session_hash is None:
        return None
    runtime_dir = "".join(char for char in runtime if char.isalnum() or char in {"-", "_"}) or "unknown"
    return _state_dir(env) / "model-context" / runtime_dir / f"{session_hash}.json"


def remember_model_context(runtime: str, payload: dict[str, Any], env: dict[str, str]) -> None:
    model = model_name(payload)
    if not model:
        return
    path = _cache_path(runtime, payload, env)
    if path is None:
        return
    record = {
        "model": model,
        "provider": provider_name(payload),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    except OSError:
        return


def payload_with_model_context(runtime: str, payload: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    if model_name(payload):
        return payload
    path = _cache_path(runtime, payload, env)
    if path is None or not path.exists():
        return payload
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return payload
    if not isinstance(loaded, dict):
        return payload
    model = _payload_value(loaded, "model")
    if not model:
        return payload
    enriched = dict(payload)
    enriched["model"] = model
    provider = _payload_value(loaded, "provider")
    if provider and not provider_name(enriched):
        enriched["provider"] = provider
    return enriched
