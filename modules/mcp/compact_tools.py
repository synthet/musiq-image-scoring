"""Compact MCP tool handlers (search, dispatch, sse_status) for stdio servers."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from modules.mcp.actions.dispatch import dispatch_action
from modules.mcp.actions.search import search_actions
from modules.mcp.names import BE_LIVE, DISPATCH
from modules.mcp.webui_client import WebuiMcpClient, call_webui_tool_sync


def _parse_csv_env(name: str) -> set[str]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return set()
    out: set[str] = set()
    for part in raw.split(","):
        p = part.strip()
        if p:
            out.add(p)
    return out


def _should_proxy_dispatch(action_id: str, local_result: dict[str, Any]) -> bool:
    allow_ids = _parse_csv_env("MCP_WEBUI_PROXY_ACTION_IDS")
    allow_prefixes = _parse_csv_env("MCP_WEBUI_PROXY_PREFIXES")

    if action_id in allow_ids:
        return True
    for pref in allow_prefixes:
        if action_id.startswith(pref):
            return True

    if local_result.get("status") == "error" and local_result.get("code") == "unknown_action":
        return True

    return False


def _webui_unavailable_error(*, action_id: str, request_id: str | None, error: str) -> dict[str, Any]:
    return {
        "status": "error",
        "code": "webui_unavailable",
        "message": (
            "WebUI MCP endpoint is unavailable. Start the WebUI (run_webui.bat or python webui.py) "
            "and ensure /mcp/sse is reachable (see GET /mcp-status → expected_sse_url)."
        ),
        "action_id": action_id,
        "request_id": request_id,
        "details": {"error": error},
    }


def handle_search(
    query: str,
    limit: int = 10,
    category: str | None = None,
    side_effect_level: str | None = None,
    read_only_only: bool = False,
    pipeline_area: str | None = None,
    include_schemas: bool = False,
    include_docs: bool = False,
    include_elevated: bool = False,
) -> dict[str, Any]:
    return search_actions(
        query,
        limit=limit,
        category=category,
        side_effect_level=side_effect_level,
        read_only_only=read_only_only,
        pipeline_area=pipeline_area,
        include_schemas=include_schemas,
        include_docs=include_docs,
        include_elevated=include_elevated,
        compact_only=True,
    )


def handle_dispatch(
    action_id: str,
    arguments: dict | None = None,
    dry_run: bool = False,
    confirmed: bool = False,
    request_id: str | None = None,
    allow_deprecated: bool = False,
    expected_version: int | None = None,
) -> dict[str, Any]:
    local = dispatch_action(
        action_id,
        arguments,
        dry_run=dry_run,
        confirmed=confirmed,
        request_id=request_id,
        allow_deprecated=allow_deprecated,
        expected_version=expected_version,
    )

    if not _should_proxy_dispatch(action_id, local):
        return local

    try:
        proxied = call_webui_tool_sync(
            DISPATCH,
            {
                "action_id": action_id,
                "arguments": dict(arguments or {}),
                "dry_run": dry_run,
                "confirmed": confirmed,
                "request_id": request_id,
                "allow_deprecated": allow_deprecated,
                "expected_version": expected_version,
            },
        )
        if isinstance(proxied, dict):
            return proxied
        return {
            "status": "success",
            "action_id": action_id,
            "request_id": request_id,
            "data": proxied,
        }
    except Exception as e:
        return _webui_unavailable_error(action_id=action_id, request_id=request_id, error=str(e))


def handle_sse_status() -> dict[str, Any]:
    client = WebuiMcpClient()
    try:
        ok, err = asyncio.run(client.probe())
        return {
            "ok": ok,
            "server": BE_LIVE,
            "url": client.url,
            "error": err,
        }
    except Exception as e:
        return {"ok": False, "server": BE_LIVE, "url": client.url, "error": str(e)}


def invoke_compact_tool(tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch a compact MCP tool by name."""
    payload = dict(args or {})
    if tool == "search":
        return handle_search(**payload)
    if tool == "dispatch":
        return handle_dispatch(**payload)
    if tool == "sse_status":
        return handle_sse_status()
    return {"status": "error", "code": "unknown_tool", "message": f"Unknown compact tool: {tool}"}
