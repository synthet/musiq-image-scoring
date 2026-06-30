"""Load and query the MCP action registry."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = ROOT / "mcp" / "action_registry.json"
PLAYWRIGHT_REGISTRY_PATH = ROOT / "mcp" / "actions" / "playwright_registry.json"
OVERLAY_PATH = ROOT / "mcp" / "actions" / "overlay.yaml"


def _require_yaml() -> Any:
    if yaml is None:
        raise RuntimeError("PyYAML required for action registry. pip install pyyaml")
    return yaml


def load_overlay(path: Path | None = None) -> dict[str, Any]:
    overlay_path = path or OVERLAY_PATH
    if not overlay_path.exists():
        raise FileNotFoundError(f"Action overlay not found: {overlay_path}")
    y = _require_yaml()
    data = y.safe_load(overlay_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid overlay format: {overlay_path}")
    return data


def build_registry_from_overlay(overlay: dict[str, Any]) -> dict[str, Any]:
    raw_actions = overlay.get("actions") or {}
    if not isinstance(raw_actions, dict):
        raise ValueError("overlay.actions must be a mapping")

    actions: list[dict[str, Any]] = []
    for action_id, record in raw_actions.items():
        if not isinstance(record, dict):
            raise ValueError(f"Invalid action record for {action_id}")
        entry = dict(record)
        entry["action_id"] = str(action_id)
        actions.append(entry)

    actions.sort(key=lambda a: a["action_id"])
    ids = [a["action_id"] for a in actions]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate action_id in overlay")

    categories: dict[str, int] = {}
    for entry in actions:
        cat = str(entry.get("category") or "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "version": overlay.get("version", 1),
        "repo": overlay.get("repo", "backend"),
        "field_weights": overlay.get("field_weights") or {},
        "categories": categories,
        "actions": actions,
    }


_registry_cache: dict[str, Any] | None = None
_registry_cache_mtime: float | None = None
_registry_cache_path: Path | None = None


def clear_registry_cache() -> None:
    """Drop cached registry (tests)."""
    global _registry_cache, _registry_cache_mtime, _registry_cache_path
    _registry_cache = None
    _registry_cache_mtime = None
    _registry_cache_path = None


def _playwright_enabled() -> bool:
    return os.environ.get("MCP_PLAYWRIGHT_ENABLED", "1").strip() != "0"


def _merge_playwright_registry(data: dict[str, Any]) -> dict[str, Any]:
    if not _playwright_enabled():
        return data
    if not PLAYWRIGHT_REGISTRY_PATH.exists():
        return data

    pw = json.loads(PLAYWRIGHT_REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(pw, dict):
        raise ValueError(f"Invalid playwright registry format: {PLAYWRIGHT_REGISTRY_PATH}")

    pw_actions = pw.get("actions") or []
    if not isinstance(pw_actions, list):
        raise ValueError("playwright_registry.actions must be a list")

    merged = dict(data)
    base_actions = list(merged.get("actions") or [])
    existing_ids = {str(a.get("action_id")) for a in base_actions if a.get("action_id")}
    for entry in pw_actions:
        if not isinstance(entry, dict):
            continue
        aid = str(entry.get("action_id") or "")
        if aid and aid not in existing_ids:
            base_actions.append(entry)
            existing_ids.add(aid)

    merged["actions"] = base_actions
    categories: dict[str, int] = {}
    for entry in base_actions:
        if not isinstance(entry, dict):
            continue
        cat = str(entry.get("category") or "unknown")
        categories[cat] = categories.get(cat, 0) + 1
    merged["categories"] = categories
    return merged


def load_action_registry(path: Path | None = None) -> dict[str, Any]:
    global _registry_cache, _registry_cache_mtime, _registry_cache_path
    registry_path = path or DEFAULT_REGISTRY_PATH
    mtime = registry_path.stat().st_mtime if registry_path.exists() else None
    if (
        path is None
        and _registry_cache is not None
        and _registry_cache_path == registry_path
        and _registry_cache_mtime == mtime
    ):
        return _registry_cache

    if registry_path.exists():
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "actions" not in data:
            raise ValueError(f"Invalid registry format: {registry_path}")
    else:
        data = build_registry_from_overlay(load_overlay())

    data = _merge_playwright_registry(data)

    if path is None:
        if _registry_cache_mtime is not None and _registry_cache_mtime != mtime:
            try:
                from modules.mcp.actions.search import reset_search_index

                reset_search_index()
            except Exception:
                pass
        _registry_cache = data
        _registry_cache_mtime = mtime
        _registry_cache_path = registry_path
    return data


def registry_actions(registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    reg = registry or load_action_registry()
    actions = reg.get("actions") or []
    if not isinstance(actions, list):
        raise ValueError("registry.actions must be a list")
    return actions


def action_by_id(action_id: str, registry: dict[str, Any] | None = None) -> dict[str, Any] | None:
    aid = (action_id or "").strip()
    for entry in registry_actions(registry):
        if entry.get("action_id") == aid:
            return entry
    return None


def action_by_legacy_name(legacy_name: str, registry: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Match legacy MCP tool name (e.g. ``execute_sql``) to a registry entry."""
    needle = (legacy_name or "").strip()
    if not needle:
        return None
    for entry in registry_actions(registry):
        if entry.get("legacy_tool_name") == needle:
            return entry
    return None


def resolve_action_id(action_id: str, registry: dict[str, Any] | None = None) -> str | None:
    """Resolve compact ``category.tool`` ids and bare legacy tool names."""
    needle = (action_id or "").strip()
    if not needle:
        return None
    if action_by_id(needle, registry):
        return needle
    legacy = action_by_legacy_name(needle, registry)
    if legacy:
        return str(legacy.get("action_id") or "")
    # ``data.execute_sql``-style guesses when category prefix is wrong but suffix matches
    if "." in needle:
        suffix = needle.rsplit(".", 1)[-1]
        legacy = action_by_legacy_name(suffix, registry)
        if legacy:
            return str(legacy.get("action_id") or "")
    else:
        # Single token: try category.tool for each known category prefix
        for entry in registry_actions(registry):
            aid = str(entry.get("action_id") or "")
            if aid.endswith(f".{needle}"):
                return aid
    return None


def suggest_actions(
    needle: str,
    *,
    registry: dict[str, Any] | None = None,
    limit: int = 5,
) -> list[dict[str, str]]:
    """Return compact action suggestions for unknown_action errors and agent hints."""
    q = (needle or "").strip().lower()
    if not q:
        return []
    scored: list[tuple[int, dict[str, str]]] = []
    for entry in registry_actions(registry):
        if not entry.get("dispatch_enabled"):
            continue
        aid = str(entry.get("action_id") or "")
        legacy = str(entry.get("legacy_tool_name") or "")
        title = str(entry.get("title") or "")
        hay = " ".join(
            [
                aid,
                legacy,
                title,
                " ".join(str(a) for a in (entry.get("aliases") or [])),
            ]
        ).lower()
        score = 0
        if aid == q or legacy == q:
            score = 100
        elif aid.endswith(f".{q}") or legacy == q.replace("_", " "):
            score = 80
        elif q in aid or (legacy and q in legacy):
            score = 60
        elif any(tok in hay for tok in q.replace(".", " ").split() if len(tok) > 2):
            score = 30
        if score:
            row: dict[str, str] = {"action_id": aid, "title": title}
            if legacy:
                row["legacy_tool_name"] = legacy
            scored.append((score, row))
    scored.sort(key=lambda x: (-x[0], x[1]["action_id"]))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for _score, row in scored:
        aid = row["action_id"]
        if aid in seen:
            continue
        seen.add(aid)
        cleaned = {k: v for k, v in row.items() if v}
        out.append(cleaned)
        if len(out) >= max(1, limit):
            break
    return out


def require_action(action_id: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    from modules.mcp.actions.errors import UnknownActionError

    resolved = resolve_action_id(action_id, registry)
    entry = action_by_id(resolved, registry) if resolved else None
    if entry:
        return entry
    suggestions = suggest_actions(action_id, registry=registry, limit=5)
    hint = (
        "Call search(query, include_schemas=True) on is-be-mcp before dispatch. "
        "Legacy raw tool names work only when registered (legacy_tool_name) or via "
        "is-be-webui with MCP_SSE_PROFILE=full."
    )
    raise UnknownActionError(
        f"Unknown action_id: {action_id}",
        details={"suggestions": suggestions, "hint": hint},
    )
