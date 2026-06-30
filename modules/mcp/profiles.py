"""MCP tool profile filtering (domain-split servers)."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, FrozenSet

from modules.mcp.catalog import load_tool_catalog, tool_by_name

logger = logging.getLogger(__name__)

VALID_PROFILES = frozenset({"full", "diagnostics", "jobs", "data", "maintenance", "router", "compact"})


def get_active_profile() -> str:
    raw = (os.environ.get("MCP_TOOL_PROFILE") or "full").strip().lower()
    if raw not in VALID_PROFILES:
        logger.warning("Unknown MCP_TOOL_PROFILE=%r; using full", raw)
        return "full"
    return raw


@lru_cache(maxsize=1)
def _catalog_profile_tools() -> dict[str, frozenset[str]]:
    cat = load_tool_catalog()
    profile_tools = cat.get("profile_tools") or {}
    out: dict[str, frozenset[str]] = {}
    for profile, names in profile_tools.items():
        if isinstance(names, list):
            out[str(profile)] = frozenset(str(n) for n in names)
    all_names: set[str] = set()
    for names in out.values():
        all_names |= set(names)
    out["full"] = frozenset(all_names)
    return out


def get_profile_tool_names(profile: str | None = None) -> FrozenSet[str]:
    prof = (profile or get_active_profile()).strip().lower()
    mapping = _catalog_profile_tools()
    if prof == "full":
        return mapping.get("full", frozenset())
    return mapping.get(prof, frozenset())


def profile_for_tool(name: str) -> str | None:
    entry = tool_by_name(name)
    if not entry:
        return None
    return str(entry.get("domain") or "")


def server_for_tool(name: str) -> str | None:
    entry = tool_by_name(name)
    if not entry:
        return None
    return str(entry.get("server") or "")


def apply_tool_profile(mcp: Any, profile: str | None = None) -> str:
    """Remove tools not in the active profile from a FastMCP instance."""
    prof = (profile or get_active_profile()).strip().lower()
    if prof in ("full", "router", "compact"):
        return prof

    allowed = get_profile_tool_names(prof)
    if not allowed:
        logger.warning("Profile %r has no tools in catalog; leaving all registered tools", prof)
        return prof

    remove = getattr(mcp, "remove_tool", None)
    if not callable(remove):
        logger.warning("FastMCP.remove_tool unavailable; cannot filter profile %r", prof)
        return prof

    names: list[str] = []
    mgr = getattr(mcp, "_tool_manager", None)
    tools_map = getattr(mgr, "_tools", None) if mgr else None
    if isinstance(tools_map, dict):
        names = list(tools_map.keys())

    removed = 0
    for name in names:
        if name not in allowed:
            remove(name)
            removed += 1

    logger.info(
        "MCP tool profile %r: kept %d tools, removed %d",
        prof,
        len(allowed & frozenset(names)),
        removed,
    )
    return prof
