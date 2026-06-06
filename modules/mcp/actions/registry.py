"""Load and query the MCP action registry."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = ROOT / "mcp" / "action_registry.json"
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


@lru_cache(maxsize=1)
def load_action_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or DEFAULT_REGISTRY_PATH
    if registry_path.exists():
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "actions" not in data:
            raise ValueError(f"Invalid registry format: {registry_path}")
        return data
    return build_registry_from_overlay(load_overlay())


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


def require_action(action_id: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    from modules.mcp.actions.errors import UnknownActionError

    entry = action_by_id(action_id, registry)
    if not entry:
        raise UnknownActionError(f"Unknown action_id: {action_id}")
    return entry
