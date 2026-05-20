"""Intra-stack embedding similarity (pgvector, default MobileNet space)."""

from __future__ import annotations

from typing import Any

from modules import db
from modules.culling_analytics._common import STACK_MEMBER_CAP, images_folder_filter, safe_float
from modules.embedding_spaces import get_default_embedding_space_id


def compute_library_embeddings(folder_id: int | None) -> dict[str, Any]:
    folder_clause, params = images_folder_filter(folder_id, alias="i")
    conn = db.get_connector()
    space_id = get_default_embedding_space_id()

    total_row = conn.query_one(
        f"SELECT COUNT(*)::int AS n FROM images i WHERE 1=1{folder_clause}",
        tuple(params),
    )
    total = int((total_row or {}).get("n") or 0)

    if space_id is None:
        return {
            "embedding_space": None,
            "coverage_pct": 0.0,
            "images_with_embedding": 0,
            "total_images": total,
            "note": "Default embedding space not registered",
        }

    emb_row = conn.query_one(
        f"""
        SELECT COUNT(DISTINCT e.image_id)::int AS n
        FROM image_embeddings e
        JOIN images i ON i.id = e.image_id
        WHERE e.embedding_space_id = ?{folder_clause}
        """,
        (space_id, *params),
    )
    with_emb = int((emb_row or {}).get("n") or 0)
    return {
        "embedding_space_id": space_id,
        "coverage_pct": round(100.0 * with_emb / total, 2) if total else 0.0,
        "images_with_embedding": with_emb,
        "total_images": total,
    }


def compute_stack_embeddings(stack_id: int) -> dict[str, Any]:
    space_id = get_default_embedding_space_id()
    if space_id is None:
        return {"available": False, "reason": "no_embedding_space"}

    conn = db.get_connector()
    ids_row = conn.query(
        """
        SELECT i.id
        FROM images i
        JOIN image_embeddings e ON e.image_id = i.id AND e.embedding_space_id = ?
        WHERE i.stack_id = ?
        LIMIT ?
        """,
        (space_id, stack_id, STACK_MEMBER_CAP),
    )
    image_ids = [int(r["id"]) for r in ids_row]
    if len(image_ids) < 2:
        return {
            "available": len(image_ids) == 1,
            "member_count": len(image_ids),
            "min_cosine_similarity": None,
            "avg_cosine_similarity": None,
            "max_cosine_similarity": None,
            "visually_mixed": False,
        }

    # Pairwise avg via SQL for moderate n (cap 50 pairs sampled)
    if len(image_ids) > 50:
        image_ids = image_ids[:50]

    placeholders = ",".join("?" * len(image_ids))
    pair_row = conn.query_one(
        f"""
        SELECT
            MIN(1 - (a.embedding <=> b.embedding)) AS min_sim,
            AVG(1 - (a.embedding <=> b.embedding)) AS avg_sim,
            MAX(1 - (a.embedding <=> b.embedding)) AS max_sim
        FROM image_embeddings a
        JOIN image_embeddings b
          ON a.embedding_space_id = b.embedding_space_id
         AND a.image_id < b.image_id
        WHERE a.embedding_space_id = ?
          AND a.image_id IN ({placeholders})
          AND b.image_id IN ({placeholders})
        """,
        (space_id, *image_ids, *image_ids),
    )
    min_s = safe_float((pair_row or {}).get("min_sim"))
    avg_s = safe_float((pair_row or {}).get("avg_sim"))
    max_s = safe_float((pair_row or {}).get("max_sim"))
    mixed_threshold = 0.85
    return {
        "available": True,
        "member_count": len(image_ids),
        "min_cosine_similarity": min_s,
        "avg_cosine_similarity": avg_s,
        "max_cosine_similarity": max_s,
        "visually_mixed": avg_s is not None and avg_s < mixed_threshold,
        "mixed_threshold": mixed_threshold,
        "truncated": len(ids_row) >= STACK_MEMBER_CAP,
    }
