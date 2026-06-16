"""Stack / sub-stack hierarchy tiers, RCA hints, and decision rollups."""

from __future__ import annotations

from typing import Any

from modules import db
from modules.culling_analytics._common import images_folder_filter
from modules.embedding_spaces import OPENCLIP_L14_IMAGE_SPACE_CODE

DEFAULT_MIN_POPULATED_STACK = 4

TIER_SINGLETON_ROOT = "singleton_root"
TIER_SINGLE_LEAF = "single_leaf"
TIER_FLAT = "flat"
TIER_POPULATED = "populated_multi_leaf"
TIER_OTHER = "other"


def classify_stack_tier(
    n: int,
    leaf_count: int,
    images_with_substack: int,
    *,
    min_populated_stack: int = DEFAULT_MIN_POPULATED_STACK,
) -> str:
    """Classify a root stack into a hierarchy tier (pure function)."""
    if n <= 0:
        return TIER_OTHER
    if n == 1:
        return TIER_SINGLETON_ROOT
    if leaf_count == 0:
        return TIER_FLAT
    if leaf_count == 1 and images_with_substack == n:
        return TIER_SINGLE_LEAF
    if leaf_count >= 2:
        return TIER_POPULATED
    return TIER_OTHER


def build_rca_hints(
    *,
    n: int,
    leaf_count: int,
    images_with_substack: int,
    embedding_coverage_pct: float | None,
    policy_versions: int,
) -> list[str]:
    """Return RCA hint codes for a stack (pure function)."""
    hints: list[str] = []
    if n == 1:
        hints.append("singleton_root")
        if images_with_substack > 0:
            hints.append("stale_sub_stack_id")
    if n >= 2 and leaf_count == 1 and images_with_substack == n:
        hints.append("single_leaf_redundant")
        if n == 2:
            hints.append("stack_size_2")
        if embedding_coverage_pct is not None and embedding_coverage_pct < 100.0:
            hints.append("embedding_fallback")
    if policy_versions > 1:
        hints.append("mixed_policy_version")
    if leaf_count >= 2 and n >= 2:
        hints.append("expected_multi_leaf")
    return hints


def _decision_counts_from_rows(rows: list[dict], *, cull: bool = True) -> dict[str, int]:
    out = {"pick": 0, "reject": 0, "neutral": 0, "unset": 0}
    for r in rows:
        if cull:
            cd = str(r.get("cull_decision") or "").strip().lower()
            if cd in ("pick", "reject", "neutral"):
                out[cd] += int(r.get("cnt") or 0)
            else:
                out["unset"] += int(r.get("cnt") or 0)
        else:
            ps = int(r.get("pick_status") or 0)
            cnt = int(r.get("cnt") or 0)
            if ps == 1:
                out["pick"] += cnt
            elif ps == -1:
                out["reject"] += cnt
            else:
                out["neutral"] += cnt
    return out


def _avg_decisions(rows: list[dict]) -> dict[str, float | None]:
    if not rows:
        return {"pick": None, "reject": None, "neutral": None}
    n = len(rows)
    return {
        "pick": sum(int(r.get("picks") or 0) for r in rows) / n,
        "reject": sum(int(r.get("rejects") or 0) for r in rows) / n,
        "neutral": sum(int(r.get("neutrals") or 0) for r in rows) / n,
    }


def compute_library_hierarchy(
    folder_id: int | None,
    *,
    min_populated_stack: int = DEFAULT_MIN_POPULATED_STACK,
    level2_space: str = OPENCLIP_L14_IMAGE_SPACE_CODE,
) -> dict[str, Any]:
    """Library-wide hierarchy stats, degenerate vs populated tiers, decision rollups."""
    folder_clause, params = images_folder_filter(folder_id)

    conn = db.get_connector()

    cull_rows = conn.query(
        f"""
        SELECT COALESCE(NULLIF(TRIM(i.cull_decision), ''), 'unset') AS cd, COUNT(*)::int AS cnt
        FROM images i
        WHERE 1=1{folder_clause}
        GROUP BY cd
        """,
        tuple(params),
    )
    library_decisions = _decision_counts_from_rows(
        [{"cull_decision": r["cd"], "cnt": r["cnt"]} for r in cull_rows]
    )

    stack_rows = conn.query(
        f"""
        SELECT
            i.stack_id,
            COUNT(*)::int AS n,
            COUNT(DISTINCT i.sub_stack_id) FILTER (WHERE i.sub_stack_id IS NOT NULL)::int AS leaf_count,
            COUNT(*) FILTER (WHERE i.sub_stack_id IS NOT NULL)::int AS images_with_substack,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'neutral')::int AS neutrals,
            COUNT(DISTINCT i.cull_policy_version)::int AS policy_versions
        FROM images i
        WHERE i.stack_id IS NOT NULL{folder_clause}
        GROUP BY i.stack_id
        """,
        tuple(params),
    )

    tier_counts: dict[str, int] = {
        TIER_SINGLETON_ROOT: 0,
        TIER_SINGLE_LEAF: 0,
        TIER_FLAT: 0,
        TIER_POPULATED: 0,
        TIER_OTHER: 0,
    }
    tier_images: dict[str, int] = {k: 0 for k in tier_counts}
    degenerate_samples: list[dict[str, Any]] = []

    for r in stack_rows:
        n = int(r["n"])
        leaf_count = int(r.get("leaf_count") or 0)
        images_with_substack = int(r.get("images_with_substack") or 0)
        tier = classify_stack_tier(
            n, leaf_count, images_with_substack, min_populated_stack=min_populated_stack
        )
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        tier_images[tier] = tier_images.get(tier, 0) + n
        if tier in (TIER_SINGLETON_ROOT, TIER_SINGLE_LEAF) and len(degenerate_samples) < 20:
            degenerate_samples.append({
                "stack_id": int(r["stack_id"]),
                "n": n,
                "leaf_count": leaf_count,
                "tier": tier,
                "rca_hints": build_rca_hints(
                    n=n,
                    leaf_count=leaf_count,
                    images_with_substack=images_with_substack,
                    embedding_coverage_pct=None,
                    policy_versions=int(r.get("policy_versions") or 1),
                ),
            })

    sub_rows = conn.query(
        f"""
        SELECT
            ss.id AS sub_stack_id,
            COUNT(i.id)::int AS n,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'neutral')::int AS neutrals
        FROM sub_stacks ss
        JOIN images i ON i.sub_stack_id = ss.id
        WHERE 1=1{folder_clause}
        GROUP BY ss.id
        """,
        tuple(params),
    )

    singleton_leaves = sum(1 for r in sub_rows if int(r["n"]) == 1)
    total_substacks = len(sub_rows)

    expected_singleton_row = conn.query_one(
        f"""
        WITH leaf_sizes AS (
            SELECT ss.id, ss.stack_id, COUNT(i.id)::int AS image_count
            FROM sub_stacks ss
            JOIN images i ON i.sub_stack_id = ss.id
            WHERE 1=1{folder_clause}
            GROUP BY ss.id, ss.stack_id
        ),
        stack_leaves AS (
            SELECT stack_id, COUNT(*)::int AS leaf_count
            FROM leaf_sizes
            GROUP BY stack_id
        )
        SELECT COUNT(*)::int AS n
        FROM leaf_sizes ls
        JOIN stack_leaves sl ON sl.stack_id = ls.stack_id
        WHERE ls.image_count = 1 AND sl.leaf_count >= 2
        """,
        tuple(params),
    )
    expected_singleton_leaves = int((expected_singleton_row or {}).get("n") or 0)

    return {
        "min_populated_stack": min_populated_stack,
        "level2_embedding_space": level2_space,
        "singleton_root_stacks": tier_counts[TIER_SINGLETON_ROOT],
        "single_leaf_stacks": tier_counts[TIER_SINGLE_LEAF],
        "flat_stacks": tier_counts[TIER_FLAT],
        "populated_multi_leaf_stacks": tier_counts[TIER_POPULATED],
        "other_stacks": tier_counts[TIER_OTHER],
        "expected_singleton_leaves": expected_singleton_leaves,
        "total_substacks": total_substacks,
        "singleton_leaves_all": singleton_leaves,
        "singleton_leaf_pct": (
            round(100.0 * singleton_leaves / total_substacks, 1) if total_substacks else 0.0
        ),
        "tiers": {
            "degenerate": {
                "singleton_root": {
                    "stacks": tier_counts[TIER_SINGLETON_ROOT],
                    "images": tier_images[TIER_SINGLETON_ROOT],
                },
                "single_leaf": {
                    "stacks": tier_counts[TIER_SINGLE_LEAF],
                    "images": tier_images[TIER_SINGLE_LEAF],
                },
                "samples": degenerate_samples,
            },
            "populated": {
                "multi_leaf": {
                    "stacks": tier_counts[TIER_POPULATED],
                    "images": tier_images[TIER_POPULATED],
                },
                "flat": {
                    "stacks": tier_counts[TIER_FLAT],
                    "images": tier_images[TIER_FLAT],
                },
            },
        },
        "decisions_by_level": {
            "library": library_decisions,
            "per_stack_avg": _avg_decisions(stack_rows),
            "per_substack_avg": _avg_decisions(sub_rows),
        },
    }


def compute_stack_hierarchy_detail(
    stack_id: int,
    *,
    min_populated_stack: int = DEFAULT_MIN_POPULATED_STACK,
    level2_space: str = OPENCLIP_L14_IMAGE_SPACE_CODE,
) -> dict[str, Any]:
    """Per-stack hierarchy tier, decisions, sub-stack breakdown, RCA hints."""
    conn = db.get_connector()

    stack_row = conn.query_one(
        """
        SELECT
            COUNT(*)::int AS n,
            COUNT(DISTINCT i.sub_stack_id) FILTER (WHERE i.sub_stack_id IS NOT NULL)::int AS leaf_count,
            COUNT(*) FILTER (WHERE i.sub_stack_id IS NOT NULL)::int AS images_with_substack,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'neutral')::int AS neutrals,
            COUNT(DISTINCT i.cull_policy_version)::int AS policy_versions
        FROM images i
        WHERE i.stack_id = ?
        """,
        (stack_id,),
    )
    if not stack_row or int(stack_row.get("n") or 0) == 0:
        return {"error": "stack_empty_or_missing", "stack_id": stack_id}

    n = int(stack_row["n"])
    leaf_count = int(stack_row.get("leaf_count") or 0)
    images_with_substack = int(stack_row.get("images_with_substack") or 0)

    emb_row = conn.query_one(
        """
        SELECT
            COUNT(DISTINCT i.id)::int AS total_ids,
            COUNT(DISTINCT ie.image_id)::int AS with_embedding
        FROM images i
        LEFT JOIN image_embeddings_768 ie
            ON ie.image_id = i.id
           AND ie.embedding_space_id = (
               SELECT id FROM embedding_spaces WHERE code = ? LIMIT 1
           )
        WHERE i.stack_id = ?
        """,
        (level2_space, stack_id),
    )
    total_emb = int((emb_row or {}).get("total_ids") or 0)
    with_emb = int((emb_row or {}).get("with_embedding") or 0)
    embedding_coverage_pct = (
        round(100.0 * with_emb / total_emb, 1) if total_emb else None
    )

    tier = classify_stack_tier(
        n, leaf_count, images_with_substack, min_populated_stack=min_populated_stack
    )
    rca_hints = build_rca_hints(
        n=n,
        leaf_count=leaf_count,
        images_with_substack=images_with_substack,
        embedding_coverage_pct=embedding_coverage_pct,
        policy_versions=int(stack_row.get("policy_versions") or 1),
    )

    substack_rows = conn.query(
        """
        SELECT
            ss.id AS sub_stack_id,
            COUNT(i.id)::int AS n,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS pick,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS reject,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'neutral')::int AS neutral
        FROM sub_stacks ss
        JOIN images i ON i.sub_stack_id = ss.id
        WHERE ss.stack_id = ?
        GROUP BY ss.id
        ORDER BY n DESC, ss.id
        """,
        (stack_id,),
    )

    return {
        "stack_id": stack_id,
        "hierarchy_tier": tier,
        "member_count": n,
        "leaf_count": leaf_count,
        "embedding_coverage_pct": embedding_coverage_pct,
        "rca_hints": rca_hints,
        "decisions": {
            "pick": int(stack_row.get("picks") or 0),
            "reject": int(stack_row.get("rejects") or 0),
            "neutral": int(stack_row.get("neutrals") or 0),
        },
        "substacks": [
            {
                "sub_stack_id": int(r["sub_stack_id"]),
                "n": int(r["n"]),
                "pick": int(r.get("pick") or 0),
                "reject": int(r.get("reject") or 0),
                "neutral": int(r.get("neutral") or 0),
            }
            for r in substack_rows
        ],
    }


def find_degenerate_stack_ids(
    folder_id: int | None,
    *,
    only: str = "all",
) -> list[int]:
    """Return stack ids matching degenerate tiers for maintenance scripts."""
    folder_clause, params = images_folder_filter(folder_id)
    conn = db.get_connector()

    having = ""
    if only == "singleton_root":
        having = "HAVING COUNT(*) = 1"
    elif only == "single_leaf":
        having = """
            HAVING COUNT(*) >= 2
               AND COUNT(DISTINCT i.sub_stack_id) FILTER (WHERE i.sub_stack_id IS NOT NULL) = 1
               AND COUNT(*) FILTER (WHERE i.sub_stack_id IS NOT NULL) = COUNT(*)
        """
    elif only == "all":
        having = """
            HAVING COUNT(*) = 1
                OR (
                    COUNT(*) >= 2
                    AND COUNT(DISTINCT i.sub_stack_id) FILTER (WHERE i.sub_stack_id IS NOT NULL) = 1
                    AND COUNT(*) FILTER (WHERE i.sub_stack_id IS NOT NULL) = COUNT(*)
                )
        """
    else:
        raise ValueError(f"unknown only filter: {only!r}")

    rows = conn.query(
        f"""
        SELECT i.stack_id
        FROM images i
        WHERE i.stack_id IS NOT NULL{folder_clause}
        GROUP BY i.stack_id
        {having}
        ORDER BY i.stack_id
        """,
        tuple(params),
    )
    return [int(r["stack_id"]) for r in rows if r.get("stack_id") is not None]
