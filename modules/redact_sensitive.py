"""Shared JSON redaction for debug bundles, MCP get_config, and support exports."""

from __future__ import annotations

from typing import Any

# Substrings (case-insensitive) on dict keys → redact values
_REDACT_KEY_SUBSTR = (
    "password",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "client_secret",
    "refresh_token",
    "access_token",
)


def redact_json_obj(obj: Any) -> Any:
    """Deep-walk JSON-like structures; replace sensitive key values with <redacted>."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if any(s in lk for s in _REDACT_KEY_SUBSTR):
                out[k] = "<redacted>"
            else:
                out[k] = redact_json_obj(v)
        return out
    if isinstance(obj, list):
        return [redact_json_obj(x) for x in obj]
    return obj
