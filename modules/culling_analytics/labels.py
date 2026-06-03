"""Color label distribution analytics."""

from __future__ import annotations

from collections import Counter
from typing import Any

from modules import db
from modules.culling_analytics._common import images_folder_filter


def compute_library_labels(folder_id: int | None) -> dict[str, Any]:
    folder_clause, params = images_folder_filter(folder_id)
    conn = db.get_connector()

    rows = conn.query(
        f"""
        SELECT COALESCE(NULLIF(TRIM(i.label), ''), '(none)') AS lbl, COUNT(*)::int AS cnt
        FROM images i
        WHERE 1=1{folder_clause}
        GROUP BY COALESCE(NULLIF(TRIM(i.label), ''), '(none)')
        """,
        tuple(params),
    )
    by_label = {str(r["lbl"]): int(r["cnt"]) for r in rows}

    mixed_stacks = conn.query_one(
        f"""
        SELECT COUNT(*)::int AS n
        FROM (
            SELECT i.stack_id
            FROM images i
            WHERE i.stack_id IS NOT NULL{folder_clause}
            GROUP BY i.stack_id
            HAVING COUNT(DISTINCT COALESCE(NULLIF(TRIM(i.label), ''), '(none)')) > 1
        ) s
        """,
        tuple(params),
    )
    mixed_count = int((mixed_stacks or {}).get("n") or 0)

    return {
        "by_label": by_label,
        "stacks_with_mixed_labels": mixed_count,
    }


def compute_stack_labels(stack_id: int) -> dict[str, Any]:
    conn = db.get_connector()
    rows = conn.query(
        """
        SELECT id, label, pick_status
        FROM images
        WHERE stack_id = ?
        """,
        (stack_id,),
    )
    labels = [str(r.get("label") or "").strip() or "(none)" for r in rows]
    counts = Counter(labels)
    majority = counts.most_common(1)[0][0] if counts else "(none)"
    picked = [r for r in rows if int(r.get("pick_status") or 0) == 1]
    picked_label_mismatch = 0
    for r in picked:
        lbl = str(r.get("label") or "").strip() or "(none)"
        if lbl != majority:
            picked_label_mismatch += 1

    return {
        "by_label": dict(counts),
        "majority_label": majority,
        "mixed_labels": len(counts) > 1,
        "picked_label_mismatch_count": picked_label_mismatch,
    }
