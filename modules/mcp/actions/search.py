"""BM25 search over MCP action registry."""

from __future__ import annotations

from typing import Any

from modules.mcp.actions.registry import load_action_registry, registry_actions
from modules.mcp.actions.schema import schema_arg_lists
from modules.mcp.bm25 import Bm25Index

LOW_CONFIDENCE_THRESHOLD = 0.35
LOW_CONFIDENCE_GAP = 0.08
_MUTATING_QUERY_HINTS = frozenset(
    {
        "rebuild",
        "export",
        "generate",
        "start",
        "thumbnail",
        "culling",
        "prune",
        "delete",
        "write",
        "submit",
    }
)

_index: Bm25Index | None = None


def reset_search_index() -> None:
    """Clear cached BM25 index (tests / registry reload)."""
    global _index
    _index = None


def _entry_for_bm25(action: dict[str, Any]) -> dict[str, Any]:
    schema = action.get("input_schema") or {}
    props = schema.get("properties") or {}
    arg_names = " ".join(str(k) for k in props.keys())
    return {
        "action_id": action.get("action_id"),
        "name": action.get("action_id"),
        "title": action.get("title"),
        "description": action.get("description"),
        "tags": action.get("tags") or [],
        "aliases": action.get("aliases") or [],
        "intent_examples": action.get("intent_examples") or [],
        "argument_names": arg_names,
        "category": action.get("category"),
        "side_effect_level": action.get("side_effect_level"),
        "dispatch_enabled": action.get("dispatch_enabled"),
        "compact_profile_exposure": action.get("compact_profile_exposure"),
    }


def _get_index() -> Bm25Index:
    global _index
    if _index is None:
        reg = load_action_registry()
        weights = reg.get("field_weights") or {
            "action_id": 4.0,
            "title": 3.0,
            "aliases": 2.5,
            "tags": 2.0,
            "intent_examples": 2.5,
            "description": 1.0,
            "argument_names": 1.5,
        }
        entries = [_entry_for_bm25(a) for a in registry_actions(reg)]
        _index = Bm25Index(entries, weights)
    return _index


def _action_corpus(action: dict[str, Any]) -> str:
    parts = [
        str(action.get("title") or ""),
        str(action.get("description") or ""),
        " ".join(str(a) for a in (action.get("aliases") or [])),
        " ".join(str(x) for x in (action.get("intent_examples") or [])),
        str(action.get("action_id") or ""),
    ]
    return " ".join(parts).lower()


def _mutating_query_low_confidence(query: str, top_action: dict[str, Any] | None) -> bool:
    if not top_action:
        return True
    q_tokens = {t.lower() for t in query.split() if len(t) > 2}
    hints = q_tokens & _MUTATING_QUERY_HINTS
    if not hints:
        return False
    corpus = _action_corpus(top_action)
    return not any(h in corpus for h in hints)


def _normalize_score(raw: float, max_raw: float) -> float:
    if max_raw <= 0:
        return 0.0
    return min(1.0, max(0.0, raw / max_raw))


def search_actions(
    query: str,
    *,
    limit: int = 10,
    category: str | None = None,
    side_effect_level: str | None = None,
    read_only_only: bool = False,
    pipeline_area: str | None = None,
    include_schemas: bool = False,
    include_docs: bool = False,
    include_elevated: bool = False,
    compact_only: bool = True,
) -> dict[str, Any]:
    del include_elevated, pipeline_area  # reserved PR1

    reg = load_action_registry()
    by_id = {a["action_id"]: a for a in registry_actions(reg)}
    q = (query or "").strip()
    if not q:
        return {"query": q, "results": [], "count": 0, "low_confidence": True}

    hits = _get_index().search(q, limit=max(1, min(limit, 50)))
    if not hits:
        return {"query": q, "results": [], "count": 0, "low_confidence": True}

    max_raw = hits[0][1] if hits else 1.0
    results: list[dict[str, Any]] = []
    for entry, raw_score in hits:
        aid = entry.get("action_id")
        action = by_id.get(aid)
        if not action:
            continue
        if not action.get("dispatch_enabled"):
            continue
        if compact_only and not action.get("compact_profile_exposure", True):
            continue
        if category and action.get("category") != category:
            continue
        if side_effect_level and action.get("side_effect_level") != side_effect_level:
            continue
        if read_only_only and action.get("side_effect_level") != "read_only":
            continue

        conf = _normalize_score(raw_score, max_raw)
        req, opt = schema_arg_lists(action.get("input_schema"))
        row: dict[str, Any] = {
            "action_id": aid,
            "title": action.get("title"),
            "description": action.get("description"),
            "category": action.get("category"),
            "side_effect_level": action.get("side_effect_level"),
            "confidence": round(conf, 4),
            "matched_fields": ["action_id", "title", "tags"],
            "required_args": req,
            "optional_args": opt,
            "dry_run_supported": bool(action.get("dry_run_supported")),
            "confirmation_required": bool(action.get("confirmation_required")),
            "canonical_docs": list(action.get("canonical_docs") or []),
            "dispatch_hint": {"action_id": aid, "args": {}},
        }
        if include_schemas:
            row["input_schema"] = action.get("input_schema")
        if include_docs:
            row["doc_snippets"] = list(action.get("canonical_docs") or [])
        results.append(row)

    low = True
    if results:
        top = results[0]["confidence"]
        second = results[1]["confidence"] if len(results) > 1 else 0.0
        low = top < LOW_CONFIDENCE_THRESHOLD or (top - second) < LOW_CONFIDENCE_GAP
        top_action = by_id.get(results[0]["action_id"])
        if _mutating_query_low_confidence(q, top_action):
            low = True

    return {
        "query": q,
        "count": len(results),
        "results": results[:limit],
        "low_confidence": low,
    }
