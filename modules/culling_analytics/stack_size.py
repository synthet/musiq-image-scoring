"""Stack size distribution metrics."""

from __future__ import annotations

from typing import Any

from modules import db
from modules.culling_analytics._common import (
    LARGE_STACK_THRESHOLD,
    images_folder_filter,
    safe_float,
)


def compute_stack_size_stats(folder_id: int | None) -> dict[str, Any]:
    folder_clause, params = images_folder_filter(folder_id)
    conn = db.get_connector()

    unstacked_row = conn.query_one(
        f"SELECT COUNT(*) AS n FROM images i WHERE i.stack_id IS NULL{folder_clause}",
        tuple(params),
    )
    unstacked = int((unstacked_row or {}).get("n") or 0)

    agg = conn.query_one(
        f"""
        WITH stack_sizes AS (
            SELECT i.stack_id, COUNT(*)::int AS cnt
            FROM images i
            WHERE i.stack_id IS NOT NULL{folder_clause}
            GROUP BY i.stack_id
        )
        SELECT
            COUNT(*)::int AS total_stacks,
            COALESCE(SUM(cnt), 0)::int AS total_stacked_images,
            MIN(cnt)::int AS min_size,
            MAX(cnt)::int AS max_size,
            AVG(cnt)::float AS avg_size,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY cnt) AS median_size,
            percentile_cont(0.10) WITHIN GROUP (ORDER BY cnt) AS p10,
            percentile_cont(0.25) WITHIN GROUP (ORDER BY cnt) AS p25,
            percentile_cont(0.75) WITHIN GROUP (ORDER BY cnt) AS p75,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY cnt) AS p90,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY cnt) AS p95,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY cnt) AS p99,
            STDDEV_POP(cnt)::float AS std_size,
            COUNT(*) FILTER (WHERE cnt = 1)::int AS singleton_stacks,
            COUNT(*) FILTER (WHERE cnt > ?)::int AS very_large_stacks
        FROM stack_sizes
        """,
        tuple(params) + (LARGE_STACK_THRESHOLD,),
    )

    if not agg or int(agg.get("total_stacks") or 0) == 0:
        return {
            "total_stacks": 0,
            "total_stacked_images": 0,
            "unstacked_images": unstacked,
            "min": None,
            "max": None,
            "avg": None,
            "median": None,
            "mode": None,
            "std": None,
            "percentiles": {},
            "interquartile_range": None,
            "singleton_stacks": 0,
            "singleton_pct": 0.0,
            "very_large_stacks": 0,
            "very_large_pct": 0.0,
            "large_stack_threshold": LARGE_STACK_THRESHOLD,
            "size_buckets": {},
        }

    total_stacks = int(agg["total_stacks"])
    singleton = int(agg.get("singleton_stacks") or 0)
    very_large = int(agg.get("very_large_stacks") or 0)
    p25 = safe_float(agg.get("p25"))
    p75 = safe_float(agg.get("p75"))
    iqr = (p75 - p25) if p25 is not None and p75 is not None else None

    mode_row = conn.query_one(
        f"""
        SELECT cnt, COUNT(*) AS freq
        FROM (
            SELECT COUNT(*)::int AS cnt
            FROM images i
            WHERE i.stack_id IS NOT NULL{folder_clause}
            GROUP BY i.stack_id
        ) s
        GROUP BY cnt
        ORDER BY freq DESC, cnt DESC
        LIMIT 1
        """,
        tuple(params),
    )
    mode_size = int(mode_row["cnt"]) if mode_row else None

    buckets_rows = conn.query(
        f"""
        SELECT
            CASE
                WHEN cnt = 1 THEN '1'
                WHEN cnt BETWEEN 2 AND 5 THEN '2-5'
                WHEN cnt BETWEEN 6 AND 10 THEN '6-10'
                WHEN cnt BETWEEN 11 AND 20 THEN '11-20'
                ELSE '21+'
            END AS bucket,
            COUNT(*)::int AS stack_count
        FROM (
            SELECT COUNT(*)::int AS cnt
            FROM images i
            WHERE i.stack_id IS NOT NULL{folder_clause}
            GROUP BY i.stack_id
        ) s
        GROUP BY bucket
        ORDER BY bucket
        """,
        tuple(params),
    )
    size_buckets = {r["bucket"]: int(r["stack_count"]) for r in buckets_rows}

    return {
        "total_stacks": total_stacks,
        "total_stacked_images": int(agg.get("total_stacked_images") or 0),
        "unstacked_images": unstacked,
        "min": int(agg.get("min_size") or 0),
        "max": int(agg.get("max_size") or 0),
        "avg": safe_float(agg.get("avg_size")),
        "median": safe_float(agg.get("median_size")),
        "mode": mode_size,
        "std": safe_float(agg.get("std_size")),
        "percentiles": {
            "p10": safe_float(agg.get("p10")),
            "p25": p25,
            "p50": safe_float(agg.get("median_size")),
            "p75": p75,
            "p90": safe_float(agg.get("p90")),
            "p95": safe_float(agg.get("p95")),
            "p99": safe_float(agg.get("p99")),
        },
        "interquartile_range": iqr,
        "singleton_stacks": singleton,
        "singleton_pct": round(100.0 * singleton / total_stacks, 2) if total_stacks else 0.0,
        "very_large_stacks": very_large,
        "very_large_pct": round(100.0 * very_large / total_stacks, 2) if total_stacks else 0.0,
        "large_stack_threshold": LARGE_STACK_THRESHOLD,
        "size_buckets": size_buckets,
    }
