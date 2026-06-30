"""Short MCP server and router tool names (is- = image scoring, be = backend)."""

from __future__ import annotations

# Cursor mcp.json server keys
BE_MCP = "is-be-mcp"
BE_ROUTER = "is-be-router"
BE_DIAG = "is-be-diag"
BE_JOBS = "is-be-jobs"
BE_DATA = "is-be-data"
BE_MAINT = "is-be-maint"
# WebUI-attached live SSE server key (preferred)
BE_LIVE = "is-be-live"
# Back-compat alias (deprecated): older configs used this name for WebUI SSE.
BE_WEBUI = "is-be-webui"
BE_FULL = "is-be-full"
BE_PG = "is-be-pg"

# Compact MCP tools
SEARCH = "search"
DISPATCH = "dispatch"
SSE_STATUS = "sse_status"

# Router meta-tools exposed to agents
BE_FIND = "be_find"
BE_DOMAINS = "be_domains"
BE_CARD = "be_card"

PROFILE_SERVER: dict[str, str] = {
    "diagnostics": BE_DIAG,
    "jobs": BE_JOBS,
    "data": BE_DATA,
    "maintenance": BE_MAINT,
    "full": BE_FULL,
    "router": BE_ROUTER,
    "compact": BE_MCP,
}


def server_for_profile(profile: str) -> str:
    return PROFILE_SERVER.get(profile, f"is-be-{profile}")
