"""
MCP router / compact server — search + dispatch (and deprecated be_* on router profile).

Usage:
    python -m modules.mcp.router_server
    MCP_TOOL_PROFILE=compact python -m modules.mcp.router_server
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

try:
    from mcp.server.fastmcp import FastMCP

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

from modules.mcp.names import BE_MCP, BE_ROUTER
from modules.mcp.router_tools import register_tools_for_profile

logger = logging.getLogger(__name__)


def _server_name() -> str:
    prof = (os.environ.get("MCP_TOOL_PROFILE") or "router").strip().lower()
    return BE_MCP if prof == "compact" else BE_ROUTER


def create_router_mcp() -> "FastMCP":
    name = _server_name()
    mcp = FastMCP(name)
    register_tools_for_profile(mcp)
    return mcp


async def run_server() -> None:
    if not MCP_AVAILABLE:
        print("Error: MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
        return
    mcp = create_router_mcp()
    await mcp.run_stdio_async()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    logger.info("Starting %s MCP server (profile=%s)...", _server_name(), os.environ.get("MCP_TOOL_PROFILE", "router"))
    asyncio.run(run_server())
