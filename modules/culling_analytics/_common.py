"""Shared helpers for culling analytics queries."""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any

from modules import config, db

LARGE_STACK_THRESHOLD = 20
STACK_MEMBER_CAP = 200
HISTOGRAM_BUCKETS = 10


def require_postgres() -> None:
    if config.get_database_engine() != "postgres":
        raise ValueError("Culling analytics requires PostgreSQL (database.engine=postgres).")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_folder_id(
    folder_path: str | None = None,
    folder_id: int | None = None,
) -> tuple[int | None, str | None]:
    """Return (folder_id, normalized_path) or (None, None) for whole library."""
    if folder_id is not None:
        row = db.get_connector().query_one("SELECT path FROM folders WHERE id = ?", (int(folder_id),))
        path = row["path"] if row else None
        return int(folder_id), path
    if folder_path and str(folder_path).strip():
        norm = os.path.normpath(str(folder_path).strip())
        row = db.get_connector().query_one("SELECT id, path FROM folders WHERE path = ?", (norm,))
        if not row:
            return None, norm
        return int(row["id"]), row.get("path") or norm
    return None, None


def images_folder_filter(folder_id: int | None, alias: str = "i") -> tuple[str, list[Any]]:
    if folder_id is None:
        return "", []
    return f" AND {alias}.folder_id = ?", [folder_id]


def safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def histogram(values: list[float], buckets: int = HISTOGRAM_BUCKETS) -> list[dict[str, Any]]:
    """Fixed [0,1] histogram; empty input returns zeroed buckets."""
    if not values:
        return [{"lo": i / buckets, "hi": (i + 1) / buckets, "count": 0} for i in range(buckets)]
    out: list[dict[str, Any]] = []
    for i in range(buckets):
        lo = i / buckets
        hi = (i + 1) / buckets
        if i == buckets - 1:
            cnt = sum(1 for v in values if lo <= v <= hi)
        else:
            cnt = sum(1 for v in values if lo <= v < hi)
        out.append({"lo": lo, "hi": hi, "count": cnt})
    return out


def percentile_from_sorted(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if p <= 0:
        return sorted_vals[0]
    if p >= 1:
        return sorted_vals[-1]
    k = (len(sorted_vals) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def summarize_numeric(values: list[float]) -> dict[str, Any]:
    clean = [v for v in values if v is not None]
    if not clean:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "avg": None,
            "median": None,
            "std": None,
            "percentiles": {},
        }
    clean.sort()
    n = len(clean)
    mean = sum(clean) / n
    var = sum((x - mean) ** 2 for x in clean) / n if n > 1 else 0.0
    pct_keys = [0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    percentiles = {f"p{int(p * 100)}": percentile_from_sorted(clean, p) for p in pct_keys}
    return {
        "count": n,
        "min": clean[0],
        "max": clean[-1],
        "avg": mean,
        "median": percentile_from_sorted(clean, 0.5),
        "std": math.sqrt(var),
        "percentiles": percentiles,
    }
