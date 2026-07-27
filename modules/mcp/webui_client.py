"""WebUI-attached MCP client helpers (SSE transport).

Used by stdio MCP servers (e.g. is-be-mcp proxy) to optionally forward calls to the
WebUI-mounted MCP endpoint at http://127.0.0.1:<port>/mcp/sse.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

try:
    from mcp.client.sse import sse_client

    from mcp import ClientSession

    MCP_CLIENT_AVAILABLE = True
except Exception:
    MCP_CLIENT_AVAILABLE = False

logger = logging.getLogger(__name__)


def _default_webui_sse_url() -> str:
    # Keep stable default; WebUI exposes /mcp/sse (see webui.py and /mcp-status).
    return (os.environ.get("IMGSCORE_WEBUI_MCP_SSE_URL") or "http://127.0.0.1:7860/mcp/sse").strip()


def _default_headers() -> dict[str, str]:
    # WebUI accepts IMGSCORE_MCP_TOKEN or MCP_TOKEN; Cursor config commonly maps
    # IMGSCORE_MCP_TOKEN into Authorization: Bearer ...
    token = (os.environ.get("IMGSCORE_MCP_TOKEN") or os.environ.get("MCP_TOKEN") or "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _extract_first_jsonish_payload(result: Any) -> Any:
    """Best-effort extract of a JSON-able payload from an MCP CallToolResult."""
    # FastMCP commonly wraps tool returns into TextContent with JSON string text.
    content = getattr(result, "content", None)
    if isinstance(content, list) and content:
        item = content[0]
        text = getattr(item, "text", None)
        if isinstance(text, str):
            s = text.strip()
            if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
                try:
                    return json.loads(s)
                except Exception:
                    return {"text": text}
            return {"text": text}

    # Some SDK versions may provide structured return directly.
    dump = getattr(result, "model_dump", None)
    if callable(dump):
        try:
            return dump()
        except Exception:
            pass
    return {"result": str(result)}


@dataclass(frozen=True)
class WebuiMcpClient:
    url: str = ""
    headers: dict[str, str] | None = None
    timeout_seconds: float = 2.5
    sse_read_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.url:
            object.__setattr__(self, "url", _default_webui_sse_url())
        if self.headers is None:
            object.__setattr__(self, "headers", _default_headers())

    async def probe(self) -> tuple[bool, str | None]:
        """Return (ok, error_message). Intended for quick health checks."""
        if not MCP_CLIENT_AVAILABLE:
            return False, "MCP client unavailable (missing mcp SDK)"
        try:
            async with sse_client(
                self.url,
                headers=dict(self.headers or {}),
                timeout=float(self.timeout_seconds),
                sse_read_timeout=float(self.sse_read_timeout_seconds),
            ) as (read, write), ClientSession(read, write) as session:
                await session.initialize()
            return True, None
        except Exception as e:
            return False, str(e)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call a tool on the WebUI MCP SSE endpoint and return its decoded payload."""
        if not MCP_CLIENT_AVAILABLE:
            raise RuntimeError("MCP client unavailable (missing mcp SDK)")

        async with sse_client(
            self.url,
            headers=dict(self.headers or {}),
            timeout=float(self.timeout_seconds),
            sse_read_timeout=float(self.sse_read_timeout_seconds),
        ) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            # Prevent long hangs: rely on HTTP timeouts + modest SSE read timeout.
            res = await session.call_tool(name, arguments=arguments or {})
            return _extract_first_jsonish_payload(res)


async def call_webui_tool(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    url: str | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 2.5,
    sse_read_timeout_seconds: float = 10.0,
) -> Any:
    """Convenience wrapper for single-shot WebUI tool calls."""
    client = WebuiMcpClient(
        url=url or "",
        headers=headers,
        timeout_seconds=timeout_seconds,
        sse_read_timeout_seconds=sse_read_timeout_seconds,
    )
    return await client.call_tool(name, arguments=arguments)


def call_webui_tool_sync(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    url: str | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 2.5,
    sse_read_timeout_seconds: float = 10.0,
) -> Any:
    """Sync wrapper (FastMCP tool functions are sync)."""
    return asyncio.run(
        call_webui_tool(
            name,
            arguments,
            url=url,
            headers=headers,
            timeout_seconds=timeout_seconds,
            sse_read_timeout_seconds=sse_read_timeout_seconds,
        )
    )

