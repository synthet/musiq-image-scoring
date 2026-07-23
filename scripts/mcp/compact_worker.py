#!/usr/bin/env python3
"""JSONL worker for Node compact MCP (is-be-mcp). One request per line on stdin."""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

# Project root: scripts/mcp -> scripts -> root
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from modules.mcp.compact_tools import invoke_compact_tool  # noqa: E402

logger = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    """Make common DB/driver types JSON-serializable for the JSONL protocol."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return bytes(obj).decode("utf-8", errors="replace")
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def dumps_response(response: dict[str, Any]) -> str:
    """Serialize a worker response; never raises for known non-JSON types."""
    return json.dumps(response, default=_json_default)


def _handle_request(raw: str) -> dict[str, Any]:
    try:
        req = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"status": "error", "code": "invalid_json", "message": str(e)}

    req_id = req.get("id")
    tool = str(req.get("tool") or "").strip()
    if not tool:
        out: dict[str, Any] = {"status": "error", "code": "missing_tool", "message": "tool is required"}
        if req_id is not None:
            out["_request_id"] = req_id
        return out

    try:
        result = invoke_compact_tool(tool, req.get("args") or {})
        if not isinstance(result, dict):
            result = {"status": "success", "data": result}
        if req_id is not None:
            result = {**result, "_request_id": req_id}
        return result
    except Exception as e:
        logger.exception("compact tool %s failed", tool)
        out = {"status": "error", "code": "handler_error", "message": str(e)}
        if req_id is not None:
            out["_request_id"] = req_id
        return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "__shutdown__":
            break
        response = _handle_request(stripped)
        try:
            payload = dumps_response(response)
        except Exception as e:
            # Last resort: keep the worker alive so Node can recover the request.
            logger.exception("failed to serialize compact response")
            fallback: dict[str, Any] = {
                "status": "error",
                "code": "serialization_error",
                "message": str(e),
            }
            req_id = response.get("_request_id") if isinstance(response, dict) else None
            if req_id is not None:
                fallback["_request_id"] = req_id
            payload = json.dumps(fallback)
        sys.stdout.write(payload + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
