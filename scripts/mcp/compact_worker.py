#!/usr/bin/env python3
"""JSONL worker for Node compact MCP (is-be-mcp). One request per line on stdin."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

# Project root: scripts/mcp -> scripts -> root
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from modules.mcp.compact_tools import invoke_compact_tool  # noqa: E402

logger = logging.getLogger(__name__)


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
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
