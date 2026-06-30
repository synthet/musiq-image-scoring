"""MCP action registry: search + dispatch."""

from modules.mcp.actions.dispatch import dispatch_action
from modules.mcp.actions.registry import (
    action_by_id,
    load_action_registry,
    registry_actions,
)
from modules.mcp.actions.search import search_actions

__all__ = [
    "action_by_id",
    "dispatch_action",
    "load_action_registry",
    "registry_actions",
    "search_actions",
]
