"""Shared helpers and constants for MCP tool implementation modules."""

from __future__ import annotations

import json
import re
from typing import Any

from modules import db

# Per-model labels reported as "missing" by ``get_failed_images``.
PER_MODEL_FAIL_LABELS = ("spaq", "ava", "liqe", "koniq", "paq2piq")
AGGREGATE_FAIL_COLUMNS = (("score_general", "general"), ("score_technical", "technical"))

IMS_OVERLAY_SUBQUERY = (
    "SELECT image_id,"
    " MAX(CASE WHEN model_name = 'spaq'    THEN COALESCE(normalized, raw_score) END) AS score_spaq,"
    " MAX(CASE WHEN model_name = 'ava'     THEN COALESCE(normalized, raw_score) END) AS score_ava,"
    " MAX(CASE WHEN model_name = 'liqe'    THEN COALESCE(normalized, raw_score) END) AS score_liqe,"
    " MAX(CASE WHEN model_name = 'koniq'   THEN COALESCE(normalized, raw_score) END) AS score_koniq,"
    " MAX(CASE WHEN model_name = 'paq2piq' THEN COALESCE(normalized, raw_score) END) AS score_paq2piq"
    " FROM image_model_scores"
    " WHERE model_name IN ('spaq','ava','liqe','koniq','paq2piq')"
    " AND is_shadow = FALSE AND status = 'success'"
    " GROUP BY image_id"
)


def sanitize_for_mcp(obj: Any) -> Any:
    """Make dict/list values JSON-safe for MCP responses (e.g. strip BLOB bytes)."""
    if hasattr(obj, "to_dict"):
        return sanitize_for_mcp(obj.to_dict())
    if hasattr(obj, "keys") and not isinstance(obj, dict):
        return {k: sanitize_for_mcp(obj[k]) for k in obj.keys()}

    if isinstance(obj, dict):
        return {k: sanitize_for_mcp(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_mcp(x) for x in obj]
    if isinstance(obj, (bytes, memoryview)):
        return f"<binary len={len(obj)}>"
    return obj


def strip_sql_comments_for_mcp(sql: str) -> str:
    """Strip leading line comments and /* */ blocks so SELECT/WITH guards work."""
    s = (sql or "").strip()
    while True:
        m = re.search(r"/\*.*?\*/", s, flags=re.DOTALL)
        if not m:
            break
        s = (s[: m.start()] + " " + s[m.end() :]).strip()
    lines_out: list[str] = []
    for line in s.splitlines():
        ls = line.strip()
        if ls.startswith("--"):
            continue
        if "--" in line:
            line = line.split("--", 1)[0].rstrip()
        if line.strip():
            lines_out.append(line)
    return " ".join(lines_out).strip()


def is_mcp_read_only_sql(normalized: str) -> bool:
    u = normalized.lstrip().upper()
    return u.startswith("SELECT") or u.startswith("WITH")


def mcp_sql_single_statement(normalized: str) -> tuple[bool, str | None]:
    core = normalized.rstrip().rstrip(";").strip()
    if ";" in core:
        return False, "Multiple SQL statements are not allowed"
    return True, None


def normalize_job_payload_for_mcp(job: dict) -> dict:
    """Copy job row to JSON-safe dict; parse queue_payload JSON and trim very long logs."""
    out = sanitize_for_mcp(dict(job))
    qp = out.get("queue_payload")
    if isinstance(qp, str) and qp.strip():
        try:
            out["queue_payload_parsed"] = json.loads(qp)
        except (json.JSONDecodeError, TypeError, ValueError):
            out["queue_payload_parsed"] = None
    log = out.get("log")
    if isinstance(log, str) and len(log) > 8000:
        out["log"] = log[-8000:]
        out["log_truncated"] = True
    return out


def registry_model_status() -> dict:
    """Per-model status from the scoring-model registry (mirrors GET /api/models)."""
    from modules.engines.registry import get_registry

    registry = get_registry()
    enabled_names = {m.name for m in registry.enabled()}
    shadow_names = {m.name for m in registry.shadow()}

    out: dict = {}
    for m in registry.all_registered():
        lo, hi = getattr(m, "score_range", (0.0, 1.0))
        out[m.name] = {
            "enabled": m.name in enabled_names,
            "shadow": m.name in shadow_names,
            "framework": getattr(m, "framework", ""),
            "version": getattr(m, "version", ""),
            "score_range": [float(lo), float(hi)],
            "load_status": getattr(m, "load_status", "unknown"),
        }
    return out
