"""Load and query the generated MCP tool catalog."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_PATH = ROOT / "mcp" / "tool_catalog.json"


@lru_cache(maxsize=1)
def load_tool_catalog(path: Path | None = None) -> dict[str, Any]:
    catalog_path = path or DEFAULT_CATALOG_PATH
    if not catalog_path.exists():
        raise FileNotFoundError(
            f"MCP tool catalog not found at {catalog_path}. "
            "Run: python scripts/generate_mcp_tool_inventory.py --update-catalog"
        )
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "tools" not in data:
        raise ValueError(f"Invalid catalog format: {catalog_path}")
    return data


def catalog_tools(catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cat = catalog or load_tool_catalog()
    tools = cat.get("tools") or []
    if not isinstance(tools, list):
        raise ValueError("catalog.tools must be a list")
    return tools


def tool_by_name(name: str, catalog: dict[str, Any] | None = None) -> dict[str, Any] | None:
    for entry in catalog_tools(catalog):
        if entry.get("name") == name:
            return entry
    return None


def domain_summary(catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cat = catalog or load_tool_catalog()
    domains_cfg = cat.get("domains") or {}
    profile_tools = cat.get("profile_tools") or {}
    rows: list[dict[str, Any]] = []
    for domain in sorted(domains_cfg.keys()):
        info = domains_cfg[domain]
        if not isinstance(info, dict):
            continue
        names = profile_tools.get(domain) or []
        rows.append(
            {
                "domain": domain,
                "server": info.get("server"),
                "tool_count": len(names) if names else info.get("tool_count", 0),
            }
        )
    return rows
