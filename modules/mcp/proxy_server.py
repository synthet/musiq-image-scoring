"""
MCP proxy stdio server (compact): local search+dispatch with optional WebUI SSE proxying.

Legacy Python stdio entrypoint. Prefer Node: mcp-server/dist/compactIndex.js
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Optional

from modules.mcp.compact_tools import handle_dispatch, handle_search, handle_sse_status
from modules.mcp.names import BE_MCP, DISPATCH, SEARCH, SSE_STATUS

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

logger = logging.getLogger(__name__)

_RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False) if MCP_AVAILABLE else None


def create_proxy_mcp() -> "FastMCP":
    if not MCP_AVAILABLE:
        raise RuntimeError("MCP SDK not installed. Run: pip install mcp")

    mcp = FastMCP(BE_MCP)

    @mcp.tool(name=SEARCH, annotations=_RO)
    def search(
        query: str,
        limit: int = 10,
        category: Optional[str] = None,
        side_effect_level: Optional[str] = None,
        read_only_only: bool = False,
        pipeline_area: Optional[str] = None,
        include_schemas: bool = False,
        include_docs: bool = False,
        include_elevated: bool = False,
    ) -> dict:
        return handle_search(
            query,
            limit=limit,
            category=category,
            side_effect_level=side_effect_level,
            read_only_only=read_only_only,
            pipeline_area=pipeline_area,
            include_schemas=include_schemas,
            include_docs=include_docs,
            include_elevated=include_elevated,
        )

    @mcp.tool(name=DISPATCH, annotations=_RO)
    def dispatch(
        action_id: str,
        arguments: Optional[dict] = None,
        dry_run: bool = False,
        confirmed: bool = False,
        request_id: Optional[str] = None,
        allow_deprecated: bool = False,
        expected_version: Optional[int] = None,
    ) -> dict:
        return handle_dispatch(
            action_id,
            arguments,
            dry_run=dry_run,
            confirmed=confirmed,
            request_id=request_id,
            allow_deprecated=allow_deprecated,
            expected_version=expected_version,
        )

    @mcp.tool(name=SSE_STATUS, annotations=_RO)
    def sse_status() -> dict:
        return handle_sse_status()

    return mcp


async def run_server() -> None:
    mcp = create_proxy_mcp()
    await mcp.run_stdio_async()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    logger.info("Starting %s MCP proxy server (stdio, compact)...", BE_MCP)
    asyncio.run(run_server())
