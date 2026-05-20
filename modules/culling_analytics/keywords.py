"""Keyword distribution and stack consistency."""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Any

from modules import db
from modules.culling_analytics._common import STACK_MEMBER_CAP, images_folder_filter


def compute_library_keywords(folder_id: int | None, *, top_n: int = 30) -> dict[str, Any]:
    folder_clause, params = images_folder_filter(folder_id, alias="i")
    conn = db.get_connector()

    top_rows = conn.query(
        f"""
        SELECT kd.keyword_display, kd.keyword_norm, COUNT(*)::int AS cnt
        FROM image_keywords ik
        JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
        JOIN images i ON i.id = ik.image_id
        WHERE 1=1{folder_clause}
        GROUP BY kd.keyword_display, kd.keyword_norm
        ORDER BY cnt DESC
        LIMIT ?
        """,
        tuple(params) + [top_n],
    )
    top = [
        {"keyword": r.get("keyword_display") or r.get("keyword_norm"), "count": int(r["cnt"])}
        for r in top_rows
    ]

    src_rows = conn.query(
        f"""
        SELECT COALESCE(ik.source, 'unknown') AS src, COUNT(*)::int AS cnt
        FROM image_keywords ik
        JOIN images i ON i.id = ik.image_id
        WHERE 1=1{folder_clause}
        GROUP BY COALESCE(ik.source, 'unknown')
        """,
        tuple(params),
    )
    by_source = {str(r["src"]): int(r["cnt"]) for r in src_rows}

    return {"top": top, "by_source": by_source}


def compute_stack_keywords(stack_id: int, *, co_occurrence_limit: int = 15) -> dict[str, Any]:
    conn = db.get_connector()
    member_rows = conn.query(
        "SELECT id FROM images WHERE stack_id = ? LIMIT ?",
        (stack_id, STACK_MEMBER_CAP),
    )
    image_ids = [int(r["id"]) for r in member_rows]
    if not image_ids:
        return {"union_keywords": [], "intersection_keywords": [], "co_occurrence_sample": []}

    placeholders = ",".join("?" * len(image_ids))
    kw_rows = conn.query(
        f"""
        SELECT ik.image_id, kd.keyword_norm
        FROM image_keywords ik
        JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
        WHERE ik.image_id IN ({placeholders})
        """,
        tuple(image_ids),
    )
    per_image: dict[int, set[str]] = {iid: set() for iid in image_ids}
    for r in kw_rows:
        per_image[int(r["image_id"])].add(str(r["keyword_norm"]))

    sets = [per_image[iid] for iid in image_ids if per_image[iid]]
    union = set().union(*sets) if sets else set()
    intersection = set.intersection(*sets) if sets else set()

    pair_counts: Counter[tuple[str, str]] = Counter()
    for s in sets:
        for a, b in combinations(sorted(s), 2):
            pair_counts[(a, b)] += 1
    co_sample = [
        {"keywords": [a, b], "count": c}
        for (a, b), c in pair_counts.most_common(co_occurrence_limit)
    ]

    picked_rows = conn.query(
        """
        SELECT DISTINCT kd.keyword_norm
        FROM image_keywords ik
        JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
        JOIN images i ON i.id = ik.image_id
        WHERE i.stack_id = ? AND i.pick_status = 1
        """,
        (stack_id,),
    )
    picked_kws = {str(r["keyword_norm"]) for r in picked_rows}
    missing_from_picked = sorted(intersection - picked_kws) if intersection else []

    return {
        "union_count": len(union),
        "intersection_count": len(intersection),
        "union_keywords": sorted(union)[:50],
        "intersection_keywords": sorted(intersection)[:50],
        "picked_missing_common_keywords": missing_from_picked[:20],
        "co_occurrence_sample": co_sample,
    }
