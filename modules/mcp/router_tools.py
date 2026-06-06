"""MCP router tools: search, dispatch, and deprecated be_* aliases."""

from __future__ import annotations

import os
from typing import Any, Optional

from modules.mcp.actions.dispatch import dispatch_action
from modules.mcp.actions.registry import action_by_id, load_action_registry, registry_actions
from modules.mcp.actions.search import search_actions
from modules.mcp.bm25 import Bm25Index, format_when_to_use
from modules.mcp.catalog import catalog_tools, domain_summary, load_tool_catalog, tool_by_name
from modules.mcp.names import (
    BE_CARD,
    BE_DOMAINS,
    BE_FIND,
    DISPATCH,
    SEARCH,
)
from modules.mcp.profiles import get_active_profile

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

_RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False) if MCP_AVAILABLE else None

_index: Bm25Index | None = None


def _get_catalog_index() -> Bm25Index:
    global _index
    if _index is None:
        cat = load_tool_catalog()
        _index = Bm25Index(catalog_tools(cat), cat.get("field_weights"))
    return _index


def _legacy_tool_result_from_action(action: dict[str, Any], score: float) -> dict[str, Any]:
    legacy = action.get("legacy_tool_name")
    name = legacy or str(action.get("action_id", "")).split(".")[-1]
    cat = action.get("category") or "diagnostics"
    reg = load_action_registry()
    domains = reg.get("categories") or {}
    server_map = {
        "diagnostics": "is-be-diag",
        "jobs": "is-be-jobs",
        "data": "is-be-data",
        "logs": "is-be-diag",
        "config": "is-be-diag",
    }
    return {
        "name": name,
        "server": server_map.get(cat, "is-be-diag"),
        "domain": cat,
        "repo": "backend",
        "risk": "read_only",
        "score": round(score, 4),
        "description": action.get("description"),
        "when_to_use": format_when_to_use(
            {
                "examples": action.get("intent_examples"),
                "tags": action.get("tags"),
                "description": action.get("description"),
            }
        ),
        "action_id": action.get("action_id"),
    }


def register_compact_tools(mcp: "FastMCP") -> None:
    """Register search + dispatch only (is-be-mcp compact profile)."""

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
        """BM25 search over dispatchable MCP actions; does not execute side effects."""
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
        """Execute a registry action by action_id with schema validation and policy checks."""
        return dispatch_action(
            action_id,
            arguments,
            dry_run=dry_run,
            confirmed=confirmed,
            request_id=request_id,
            allow_deprecated=allow_deprecated,
            expected_version=expected_version,
        )


def register_router_tools(mcp: "FastMCP") -> None:
    """Register compact tools plus deprecated be_* aliases on is-be-router."""
    register_compact_tools(mcp)

    @mcp.tool(name=BE_FIND, annotations=_RO)
    def be_find(
        query: str,
        limit: int = 10,
        domain: Optional[str] = None,
        repo: Optional[str] = None,
        risk: Optional[str] = None,
    ) -> dict:
        """Deprecated: use search(). BM25 over legacy tool catalog for server dispatch."""
        del repo
        hits = _get_catalog_index().search(
            query,
            limit=max(1, min(limit, 50)),
            domain=domain,
            risk=risk,
        )
        results = []
        for entry, score in hits:
            results.append(
                {
                    "name": entry.get("name"),
                    "server": entry.get("server"),
                    "domain": entry.get("domain"),
                    "repo": entry.get("repo"),
                    "risk": entry.get("risk"),
                    "score": round(score, 4),
                    "description": entry.get("description"),
                    "when_to_use": format_when_to_use(entry),
                }
            )
        compact = search_actions(query, limit=limit, category=domain, compact_only=True)
        for row in compact.get("results") or []:
            action = action_by_id(row.get("action_id") or "")
            if not action:
                continue
            legacy = _legacy_tool_result_from_action(action, float(row.get("confidence") or 0))
            if risk and legacy.get("risk") != risk:
                continue
            if not any(r.get("action_id") == action.get("action_id") for r in results):
                results.append(legacy)
        return {
            "query": query,
            "count": len(results),
            "results": results[:limit],
            "deprecated": True,
            "hint": "Prefer is-be-mcp search() + dispatch(action_id, args).",
        }

    @mcp.tool(name=BE_DOMAINS, annotations=_RO)
    def be_domains() -> dict:
        """Deprecated: use search(). List action categories and legacy MCP domains."""
        reg = load_action_registry()
        cat = load_tool_catalog()
        action_cats = reg.get("categories") or {}
        domains = [
            {"domain": k, "action_count": v, "source": "action_registry"}
            for k, v in sorted(action_cats.items())
        ]
        return {
            "repo": reg.get("repo"),
            "action_categories": domains,
            "legacy_domains": domain_summary(cat),
            "deprecated": True,
            "hint": f"Prefer {SEARCH}(query) then {DISPATCH}(action_id, args) on is-be-mcp.",
        }

    @mcp.tool(name=BE_CARD, annotations=_RO)
    def be_card(name: str) -> dict:
        """Deprecated: use search(include_schemas=True) or dispatch dry_run."""
        needle = name.strip()
        for action in registry_actions():
            if action.get("action_id") == needle or action.get("legacy_tool_name") == needle:
                return {
                    "tool": action,
                    "when_to_use": format_when_to_use(
                        {
                            "examples": action.get("intent_examples"),
                            "tags": action.get("tags"),
                        }
                    ),
                    "deprecated": True,
                    "hint": f"Prefer {SEARCH} or {DISPATCH}.",
                }
        entry = tool_by_name(needle)
        if not entry:
            return {
                "error": f"Unknown tool or action: {name}",
                "hint": f"Use {SEARCH} with a natural language query.",
            }
        return {"tool": entry, "when_to_use": format_when_to_use(entry), "deprecated": True}


def register_tools_for_profile(mcp: "FastMCP", profile: str | None = None) -> None:
    prof = (profile or get_active_profile() or os.environ.get("MCP_TOOL_PROFILE") or "router").strip().lower()
    if prof == "compact":
        register_compact_tools(mcp)
    else:
        register_router_tools(mcp)
