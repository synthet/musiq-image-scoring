"""MCP tool routing: catalog, BM25 search, and profile filtering."""

from modules.mcp.catalog import load_tool_catalog
from modules.mcp.profiles import (
    VALID_PROFILES,
    apply_tool_profile,
    get_active_profile,
    get_profile_tool_names,
    profile_for_tool,
    server_for_tool,
)

__all__ = [
    "VALID_PROFILES",
    "apply_tool_profile",
    "get_active_profile",
    "get_profile_tool_names",
    "load_tool_catalog",
    "profile_for_tool",
    "server_for_tool",
]
